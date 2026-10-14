"""Poll TRAPP for transcription assignments given to the bot account, read every line with the ROAD HTR API,
write the text back to each annotation and submit the page for review.

    python pipeline.py                 # run forever
    python pipeline.py --once          # one pass over the open assignments, then exit
    python pipeline.py --assignment 20581 --dry-run
"""
import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import localsettings as settings
from utils import ApiNotReady, Reader, Trapp, TrappError, crop_box, fetch, iiif_region_url

log = logging.getLogger('middleman')

POLL_SECONDS = getattr(settings, 'poll_seconds', 30)
MAX_POLL_SECONDS = getattr(settings, 'max_poll_seconds', 600)
LINE_WORKERS = getattr(settings, 'line_workers', 4)
MAX_FAILURES = getattr(settings, 'max_failures', 3)
OVERWRITE = getattr(settings, 'overwrite_existing', False)
IIIF_SIZE = getattr(settings, 'iiif_size', 'max')
SKIP = set(getattr(settings, 'skip_assignments', []))
INFER_TIMEOUT = getattr(settings, 'infer_timeout', 600)


def existing_text(annotation):
    return (annotation.get('content') or annotation.get('text_content') or '').strip()


def read_line(reader, image_uri, annotation, width, height):
    box = crop_box(annotation, width, height)
    if box is None:
        raise ValueError(f'annotation {annotation["id"]} has no usable region')
    url = iiif_region_url(image_uri, box, IIIF_SIZE)
    return reader.transcribe(fetch(url))['prediction']


def process(trapp, reader, assignment, dry_run=False):
    assignment_id, image_id = assignment['id'], assignment['object_id']
    started = time.monotonic()
    log.info('assignment %s: image %s (%s)', assignment_id, image_id, assignment.get('target_display', ''))
    if assignment['status']['name'] == 'assigned' and not dry_run:
        trapp.set_status(assignment_id, 'in_progress')
    image = trapp.image(image_id)
    image_uri = image.get('iiif_image_id')
    if not image_uri:
        raise ValueError(f'image {image_id} has no IIIF image URI')
    annotations = sorted(trapp.annotations(image_id) or [], key=lambda a: (a.get('page_order') is None, a.get('page_order') or 0, a['id']))
    todo = [a for a in annotations if OVERWRITE or not existing_text(a)]
    log.info('assignment %s: %d lines, %d to read', assignment_id, len(annotations), len(todo))

    def one(annotation):
        text = read_line(reader, image_uri, annotation, image.get('width'), image.get('height'))
        if dry_run:
            log.info('  [%s] %s', annotation['id'], text)
        else:
            trapp.set_text(annotation['id'], text)
        return annotation['id'], text

    errors = {}
    with ThreadPoolExecutor(max_workers=LINE_WORKERS) as pool:
        futures = {pool.submit(one, a): a['id'] for a in todo}
        for future, annotation_id in futures.items():
            try:
                future.result()
            except ApiNotReady:
                for f in futures:
                    f.cancel()
                raise
            except Exception as error:
                errors[annotation_id] = str(error)
                log.warning('assignment %s: line %s failed: %s', assignment_id, annotation_id, error)
    if errors:
        raise RuntimeError(f'{len(errors)} of {len(todo)} lines failed; not submitted')
    if not dry_run:
        trapp.set_status(assignment_id, 'submitted_for_review')
    log.info('assignment %s: %s in %.0f s', assignment_id, 'read (dry run)' if dry_run else 'submitted for review',
             time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--once', action='store_true', help='one pass over the open assignments, then exit')
    parser.add_argument('--assignment', type=int, action='append', help='only this assignment id (repeatable)')
    parser.add_argument('--dry-run', action='store_true', help='read and log the lines; write nothing to TRAPP')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    trapp = Trapp(settings.base_url, settings.username, settings.password)
    reader = Reader(settings.infer_base_url, timeout=INFER_TIMEOUT)
    trapp.login()
    health = reader.health()
    log.info('transcription API: %s (%s of %s readers ready)', health.get('status'), health.get('ready', '?'),
             health.get('total', '?'))

    failures = {}
    wait = POLL_SECONDS
    while True:
        try:
            assignments = trapp.open_assignments(settings.agent_id)
        except TrappError as error:
            log.error('could not list assignments: %s', error)
            assignments = None
        if assignments is not None:
            if args.assignment:
                assignments = [a for a in assignments if a['id'] in args.assignment]
            todo = [a for a in assignments if a['id'] not in SKIP and failures.get(a['id'], 0) < MAX_FAILURES]
            log.info('%d open assignments, %d to do', len(assignments), len(todo))
            done_any = False
            for assignment in todo:
                try:
                    process(trapp, reader, assignment, args.dry_run)
                    done_any = True
                except ApiNotReady as error:
                    log.warning('%s; pausing', error)
                    break
                except Exception as error:
                    failures[assignment['id']] = failures.get(assignment['id'], 0) + 1
                    log.error('assignment %s failed (%d of %d tries): %s', assignment['id'],
                              failures[assignment['id']], MAX_FAILURES, error)
            wait = POLL_SECONDS if done_any else min(wait * 2, MAX_POLL_SECONDS)
        else:
            wait = min(wait * 2, MAX_POLL_SECONDS)
        if args.once or args.dry_run:
            return 0
        log.info('next check in %d s', wait)
        time.sleep(wait)


if __name__ == '__main__':
    sys.exit(main())

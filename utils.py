import base64
import logging
import time

import requests

log = logging.getLogger('middleman')


class TrappError(RuntimeError):
    pass


class ApiNotReady(RuntimeError):
    pass


class Trapp:
    def __init__(self, base_url, username, password, timeout=60, retries=4):
        self.base_url = base_url.rstrip('/') + '/'
        self.username = username
        self.password = password
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json'})

    def login(self):
        try:
            r = self.session.post(self.base_url + 'token/', json={'username': self.username, 'password': self.password},
                                  timeout=self.timeout)
        except requests.RequestException as error:
            raise TrappError(f'login failed: {error}')
        if r.status_code != 200:
            raise TrappError(f'login failed ({r.status_code}): {r.text[:200]}')
        self.session.headers['Authorization'] = f'Bearer {r.json()["access"]}'
        log.info('logged in to TRAPP as %s', self.username)

    def request(self, method, path, **kwargs):
        url = path if path.startswith('http') else self.base_url + path.lstrip('/')
        relogged = False
        error = None
        for attempt in range(self.retries):
            if attempt:
                time.sleep(min(30, 2 ** attempt))
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as e:
                error = str(e)
                continue
            if r.status_code in (401, 403) and not relogged:
                self.login()
                relogged = True
                continue
            if r.status_code >= 500:
                error = f'{r.status_code}: {r.text[:200]}'
                continue
            if not r.ok:
                raise TrappError(f'{method} {url} -> {r.status_code}: {r.text[:300]}')
            return r.json() if r.content else None
        raise TrappError(f'{method} {url} failed after {self.retries} tries: {error}')

    def paged(self, path, params=None):
        url = path
        while url:
            page = self.request('GET', url, params=params)
            params = None
            yield from page['results']
            url = page.get('next')

    def open_assignments(self, user_id):
        return [a for a in self.paged('assignments/', {'assigned_to': user_id})
                if a['status']['name'] in ('assigned', 'in_progress')
                and a.get('workflow_type_name') == 'transcription']

    def set_status(self, assignment_id, status):
        return self.request('PATCH', f'assignments/{assignment_id}/', json={'status': status})

    def image(self, image_id):
        return self.request('GET', f'image/{image_id}/')

    def annotations(self, image_id):
        return self.request('GET', 'annotations/', params={'image': image_id})

    def set_text(self, annotation_id, text):
        return self.request('PATCH', f'annotations/{annotation_id}/', json={'content': text})


class Reader:
    def __init__(self, infer_url, timeout=600):
        self.infer_url = infer_url
        self.health_url = infer_url.rstrip('/').rsplit('/', 1)[0] + '/health'
        self.timeout = timeout
        self.session = requests.Session()

    def health(self):
        try:
            return self.session.get(self.health_url, timeout=30).json()
        except (requests.RequestException, ValueError) as error:
            return {'status': 'unreachable', 'error': str(error)}

    def transcribe(self, image_bytes):
        payload = {'image_base64': base64.b64encode(image_bytes).decode('ascii')}
        try:
            r = self.session.post(self.infer_url, json=payload, timeout=self.timeout)
        except requests.RequestException as error:
            raise ApiNotReady(f'transcription API unreachable: {error}')
        if r.status_code == 503:
            raise ApiNotReady(f'transcription API not ready: {r.text[:300]}')
        if not r.ok:
            raise RuntimeError(f'transcription API error {r.status_code}: {r.text[:300]}')
        return r.json()


def crop_box(annotation, width=None, height=None):
    selector = (annotation.get('annotation_data') or {}).get('target', {}).get('selector') or {}
    geometry = selector.get('geometry') or {}
    bounds = geometry.get('bounds')
    if bounds:
        x0, y0, x1, y1 = bounds['minX'], bounds['minY'], bounds['maxX'], bounds['maxY']
    elif all(k in geometry for k in ('x', 'y', 'w', 'h')):
        x0, y0 = geometry['x'], geometry['y']
        x1, y1 = x0 + geometry['w'], y0 + geometry['h']
    elif geometry.get('points'):
        xs = [float(p[0]) for p in geometry['points']]
        ys = [float(p[1]) for p in geometry['points']]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    else:
        return None
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = int(round(x1)), int(round(y1))
    if width:
        x1 = min(x1, int(width))
    if height:
        y1 = min(y1, int(height))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return x0, y0, x1 - x0, y1 - y0


def iiif_region_url(image_uri, box, size='max'):
    base = image_uri.rstrip('/')
    if base.endswith('/info.json'):
        base = base[:-len('/info.json')]
    x, y, w, h = box
    return f'{base}/{x},{y},{w},{h}/{size}/0/default.jpg'


def fetch(url, timeout=120, retries=3):
    error = None
    for attempt in range(retries):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            r = requests.get(url, timeout=timeout)
        except requests.RequestException as e:
            error = str(e)
            continue
        if r.ok:
            return r.content
        error = f'{r.status_code}: {r.text[:200]}'
        if r.status_code < 500:
            break
    raise RuntimeError(f'could not fetch {url}: {error}')

# road_htr_middleman

Moves work between TRAPP and the ROAD HTR API (`run_api.sh` in road-zindi-Darius-Moruri).

For every open transcription assignment of the bot user (`agent_id`, status `assigned` or `in_progress`):

1. marks it `in_progress`;
2. crops each line annotation of the page from the IIIF server (the annotation's bounding box);
3. sends the crop to the API and writes the answer to the annotation's `content`;
4. marks the assignment `submitted_for_review`, which hands it to a human transcriber.

Lines that already have text are skipped unless `overwrite_existing = True`, so an interrupted page resumes where
it stopped. A page with any failed line is left `in_progress` and retried on later passes (up to `max_failures`).
When the API is loading or unreachable the pass pauses and tries again later.

```
pip install -r requirements.txt
cp localsettings.example.py localsettings.py   # then fill in
python pipeline.py --assignment 20581 --dry-run   # read one page, write nothing
python pipeline.py --once
python pipeline.py
```

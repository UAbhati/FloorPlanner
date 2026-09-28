# my_bedroom_repeat (second capture of my_bedroom)

Same physical bedroom as `samples/local/my_bedroom`, re-captured later for the
**repeatability gate** (spec: two captures at the same tier agree within
1 cm / 0.5% per wall).

Uses the same tape GT as `my_bedroom` via `GT_ROOM_ALIASES` in
`reconstruction/media_layout.py` (folder name ≠ primary `room_id`).

## Files
- `photos/` — overlapping stills (second walk)
- `video.mp4` — handheld walkthrough (second walk)

## Run
```bash
python run.py --input samples/local/my_bedroom --tier photo --out out/
python run.py --input samples/local/my_bedroom_repeat --tier photo --out out/
python run.py --input samples/local/my_bedroom --tier video --out out/
python run.py --input samples/local/my_bedroom_repeat --tier video --out out/
```

Compare wall lengths / ceiling across the pair; see `benchmark/REPORT.md`
§ Repeatability.

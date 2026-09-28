# my_bedroom_repeat (second capture of my_bedroom)

Same physical bedroom as `samples/my_bedroom`, re-captured later for the
**repeatability gate** (spec: two captures at the same tier agree within
1 cm / 0.5% per wall).

Uses the same tape GT as `my_bedroom` via `GT_ROOM_ALIASES` in
`reconstruction/media_layout.py` (folder name ≠ primary `room_id`).

## Files
- `photos/` — overlapping stills (second walk)
- `video.mp4` — handheld walkthrough (second walk)

## Run
```bash
python run.py --input samples/my_bedroom --tier photo --no-colmap --out out/
python run.py --input samples/my_bedroom_repeat --tier photo --no-colmap --out out/
python run.py --input samples/my_bedroom --tier video --no-colmap --out out/
python run.py --input samples/my_bedroom_repeat --tier video --no-colmap --out out/
```

Compare wall lengths / ceiling across the pair; see `benchmark/REPORT.md`
§ Repeatability.

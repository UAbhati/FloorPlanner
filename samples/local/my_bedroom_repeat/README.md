# my_bedroom_repeat

Same bedroom as `samples/local/my_bedroom`, walked again later for the
repeatability gate (two captures at the same tier should agree within
1 cm / 0.5% per wall).

Reuses the `my_bedroom` tape row via `GT_ROOM_ALIASES` in
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

Compare wall lengths / ceiling across the pair — details in
`benchmark/REPORT.md` § Repeatability.

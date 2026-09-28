# my_bedroom

Android capture of the bedroom next to the hall — photo / video + tape GT.
Door on the north wall opens into `my_room`.

## Layout (tape)

| Item | Value |
|------|--------|
| West / East walls | **1.95 m** |
| South / North walls | **2.43 m** |
| Floor area | ≈ **4.74 m²** |
| North opening | door to hall **0.88 m** |

## Files

- `photos/` — overlapping stills
- `video.mp4` — handheld walkthrough
- GT: `../../benchmark/ground_truth.csv` (`room_id=my_bedroom`)

## Run

```bash
python run.py --input samples/local/my_bedroom --tier photo --out out/
python run.py --input samples/local/my_bedroom --tier video --out out/
# Stitch with hall
python run.py --stitch-gt my_room,my_bedroom --tier photo --drift-align on --out out/stitch
```

# my_bedroom (Android bedroom capture)

Adjacent rectangle room used for **photo** / **video** tiers + tape GT.
Door on the north wall into `my_room` (hall).

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
python run.py --input samples/my_bedroom --tier photo --no-colmap --out out/
python run.py --input samples/my_bedroom --tier video --no-colmap --out out/
# Stitch with hall
python run.py --stitch-gt my_room,my_bedroom --tier photo --drift-align on --out out/stitch
```

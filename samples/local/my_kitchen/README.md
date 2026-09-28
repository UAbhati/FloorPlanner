# my_kitchen

Third room on the property, off `my_room` (hall) — this is how I hit the
“3+ rooms plus a connector” multi-room requirement.
Door sits on the west wall of the hall / east wall of the kitchen.

## Layout (tape / Magicplan app export)

| Item | Value |
|------|--------|
| North / South walls | **2.25 m** |
| East / West walls | **1.66 m** |
| Floor area | ≈ **3.735 m²** (app says 3.74 m²) |
| Ceiling height | **2.58 m** (same slab as hall / bedroom) |
| East opening | door to hall **0.77 m** |

## Files

- `photos/` — 12 overlapping stills
- `video.mp4` — handheld walkthrough (~30s)
- GT: `../../benchmark/ground_truth.csv` (`room_id=my_kitchen`)

## Run

```bash
python run.py --input samples/local/my_kitchen --tier photo --out out/
python run.py --input samples/local/my_kitchen --tier video --out out/
# Stitch all three (hall is hub; bedroom south, kitchen west)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
```

## Honest note

I tried COLMAP here too — too thin (327 plane inliers on photos, 121 on video
frames vs the 500 I require). Same fallback as `my_room` / `my_bedroom`:
axis-aligned rectangle from tape/app `length_m`/`width_m`, with tier CIs
(±8% photo, ±3% video).

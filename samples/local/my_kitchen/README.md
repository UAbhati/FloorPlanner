# my_kitchen (Android kitchen capture)

Third room in the property, connected to `my_room` (hall) — completes the
"3+ rooms plus a connector" multi-room benchmark requirement.
Door on the west wall of `my_room` / east wall of `my_kitchen`.

## Layout (tape / Magicplan app export)
| Item | Value |
|------|--------|
| North / South walls | **2.25 m** |
| East / West walls | **1.66 m** |
| Floor area | ≈ **3.735 m²** (app reports 3.74 m²) |
| Ceiling height | **2.58 m** (same slab as `my_room` / `my_bedroom`) |
| East opening | door to hall **0.77 m** |

## Files
- `photos/` — 12 overlapping stills
- `video.mp4` — handheld walkthrough (~30s)
- GT: `../../benchmark/ground_truth.csv` (`room_id=my_kitchen`)

## Run
```bash
python run.py --input samples/local/my_kitchen --tier photo --out out/
python run.py --input samples/local/my_kitchen --tier video --out out/
# Stitch all three rooms (hall is the star center; bedroom south, kitchen west)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
```

## Honest note
COLMAP was attempted and is too thin here too (327 plane inliers on photos,
121 on video frames vs. the 500 required) — same fallback as `my_room` /
`my_bedroom`: an axis-aligned rectangle anchored to the tape/app-measured
`length_m`/`width_m`, with tier-calibrated wall CIs (±8% photo, ±3% video).

# my_room (Android hall capture)

Rectangle hall used for **photo** and **video** tiers + tape ground truth.
Not a Stray Scanner LiDAR capture.

## Layout (tape, corrected 2026-09-27)
| Item | Value |
|------|--------|
| Ceiling height | 2.58 m (one spot) |
| North / South walls | **4.82 m** (482 cm) |
| East / West walls | 2.42 m |
| Floor area | ≈ **11.66 m²** |
| South openings | door **0.88 m**, passage **0.77 m** |

Adjacent **bedroom**: `samples/my_bedroom` (photos + video). Tape 1.95 m × 2.43 m, door 0.88 m to hall (`room_id=my_bedroom` in GT).

## Capture notes
- Primary set: windows without curtains blocking.
- COLMAP on this hall is typically too thin → tape-scaled rectangle with photo ±8% / video ±3% CIs.

## Files
- `photos/` — overlapping stills
- `video.mp4` — handheld walkthrough
- GT: `../../benchmark/ground_truth.csv`
- Head-to-head: `../../benchmark/h2h/`

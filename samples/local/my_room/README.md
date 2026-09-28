# my_room

My Android capture of the hall — photo + video tiers, with tape ground truth.
Not a Stray LiDAR scan.

## Layout (tape, corrected 2026-09-27)

| Item | Value |
|------|--------|
| Ceiling height | 2.58 m (one spot) |
| North / South walls | **4.82 m** (482 cm) |
| East / West walls | 2.42 m |
| Floor area | ≈ **11.66 m²** |
| South openings | door **0.88 m**, passage **0.77 m** |

Bedroom next door: `samples/local/my_bedroom` (photos + video). Tape 1.95 m × 2.43 m,
door 0.88 m into the hall (`room_id=my_bedroom` in GT).

## Capture notes

- Primary set: windows without curtains blocking the view.
- COLMAP on this hall is usually too thin, so I fall back to a tape-scaled rectangle
  with photo ±8% / video ±3% CIs.

## Files

- `photos/` — overlapping stills
- `video.mp4` — handheld walkthrough
- GT: `../../benchmark/ground_truth.csv`
- Head-to-head: `../../benchmark/h2h/`

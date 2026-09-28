# COLMAP notes (photo / video)

I wanted photo/video to run on COLMAP without silently falling back to GT.

## Where things landed

- Default **100 frames** from video (long walks auto-raise spacing so overlap doesn’t collapse).
- COLMAP mapper settings are relaxed for indoors.
- If reconstruction is thin → **fail honestly**. No GT-rectangle bypass on the production path.
- Metric scale still needs `--ref-length-m` (tape) or `--ref-from` (a prior LiDAR run). That’s intentional.
- On company Stray `*_rgb` siblings, short-wall lands within ±5% of the LiDAR golden after scale (see `benchmark/colmap_validation/`).

My own Android rooms (`my_room` / bedroom / kitchen) are still too thin for COLMAP — those benchmark rows use the tape rectangle path and say so in `benchmark/REPORT.md`.

## What I tried / why thin rooms fail

- Too few reconstructed points on plain phone stills / short clips.
- Sparse frame sampling used to make it worse (fixed by denser extract).
- Texture-poor walls don’t give SIFT much to work with.
- Exhaustive matching on video is slow; sequential is a better fit for walkthroughs.

## If I pick this up again

1. More stills per room (~8+ overlapping; denser if SfM stays thin) and longer slow video walks.
2. Sequential / vocab-tree matching for video.
3. Keep the honest thin-SfM fail — don’t quietly substitute GT.

Known limit I won’t paper over: **one reference length is still required for metric scale** on plain phone captures.

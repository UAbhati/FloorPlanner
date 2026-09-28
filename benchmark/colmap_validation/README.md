# COLMAP validation harness

Compare LiDAR golden JSON against photo/video COLMAP output from RGB-only samples.

## Workflow

```bash
# Golden
python run.py --input samples/stray/single_room --tier lidar

# COLMAP on RGB video (default --colmap-frames 100)
python run.py --input samples/stray/single_room_rgb --tier video \
  --ref-from out/single_room/

# Compare (writes out/comparison.json; exit 0 on PASS)
python run.py --compare out/single_room/ out/single_room_rgb/
```

## Pass criteria

| Metric | Gate |
|--------|------|
| Wall lengths (sorted) | ±5% vs LiDAR |
| Floor area | ±10% vs LiDAR |
| Wall count | exact match |

Long walls often show ~0% error because COLMAP is scaled to the LiDAR longest
wall (`--ref-from`). Short-wall / area error is the real signal.

## Baseline notes (2026-09-28)

| Setup | `single_room` area err | Short-wall err |
|-------|------------------------|----------------|
| 16 frames, exhaustive | mapper fail | — |
| 100 frames, sequential+SIFT | ~8.7% (area PASS) | ~8.7% (wall FAIL vs 5%) |

See also `docs/STRAY_COLMAP_VALIDATION_PLAN.md`.

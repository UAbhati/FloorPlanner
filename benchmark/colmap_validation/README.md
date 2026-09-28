# COLMAP validation harness

Compare LiDAR golden JSON against photo/video COLMAP output from RGB-only samples.

## Workflow

```bash
# Golden
python run.py --input samples/stray/single_room --tier lidar

# COLMAP on RGB video (default --colmap-frames 100; long videos auto-raise)
python run.py --input samples/stray/single_room_rgb --tier video \
  --ref-from out/single_room/

# Compare → out/comparison.json + out/comparison.png
python run.py --compare out/single_room/ out/single_room_rgb/
```

**Note:** Area/wall error is sensitive to the extracted frame set. Prefer the
default 100 frames for short Stray clips; bump only for long walks. Accuracy
tuning is deferred — core path (LiDAR golden, RGB COLMAP, compare) is complete.

## Pass criteria

| Metric | Gate |
|--------|------|
| Wall lengths (sorted) | ±5% vs LiDAR |
| Floor area | ±10% vs LiDAR |
| Wall count | exact match |

Long walls often show ~0% error because COLMAP is scaled to the LiDAR longest
wall (`--ref-from`). Short-wall / area error is the real signal.

## Results (2026-09-28 evening)

Improvements: sequential matcher (auto), soft SfM floor RANSAC, duration-aware
frame density, flat-cloud wall-band fallback.

| Sample | Frames | Area err | Short-wall err | Verdict |
|--------|--------|----------|----------------|---------|
| `single_room` | 100 | **0.0%** | **0.0%** | **PASS** |
| `single_scan_floor` | 150 | **6.5%** (area PASS) | 6.5% | FAIL walls (±5%) |
| `single_scan_with_ceiling` | 250 | 13.9% | 13.9% | FAIL (was: no model) |

## Next

- Push floor short-walls under ±5%; ceiling under ±10% area
- Optional side-by-side plan plots (Phase 4)

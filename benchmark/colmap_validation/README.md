# COLMAP validation harness

Compare LiDAR golden JSON against photo/video COLMAP output from RGB-only samples.

## Workflow

```bash
# Golden
python run.py --input samples/stray/single_room --tier lidar

# COLMAP on RGB video (default --colmap-frames 100; long videos auto-raise to ≤1.0s spacing)
python run.py --input samples/stray/single_room_rgb --tier video \
  --ref-from out/single_room/

# Compare → comparison.json + comparison.png
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

## Results (2026-09-28)

Sparse-fit changes: deterministic PCA-up band, polar rect on band vs all-points
(pick larger short/long aspect), duration-aware frames (≤1.0s spacing, cap 300).

| Sample | Frames | Area err | Short-wall err | Verdict |
|--------|--------|----------|----------------|---------|
| `single_room` | 100 | **2.8%** | **2.8%** | **PASS** |
| `single_scan_floor` | 150 | **1.5%** | **1.5%** | **PASS** |
| `single_scan_with_ceiling` | 215 | **1.8%** | **1.8%** | **PASS** |

Artifacts: `*_comparison.json` in this folder (plus `out/*/comparison.json` from local runs).

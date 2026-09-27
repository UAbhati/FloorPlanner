# Company Stray Scanner LiDAR samples

Provided captures (no tape GT from us). Pipeline uses odometry + depth + confidence.

| Sample | Role | Notes from our runs |
|--------|------|---------------------|
| `single_room` | Furnished single room | ~9.9 m² `manhattan_rect`; ceiling soft-fails (furniture plane ~1.25 m) → prior CI |
| `single_scan_floor` | Floor-heavy walk | ~27.0 m² `manhattan_rect`; ceiling ~1.83 m |
| `single_scan_with_ceiling` | Ceiling covered | ~30.5 m² `manhattan_rect`; ceiling ~1.83 m; fix-loop capture |

## Run all tiers (same folder)
```bash
python run.py --input samples/single_room --tier lidar --out out/
python run.py --input samples/single_room --tier photo --out out/
python run.py --input samples/single_room --tier video --out out/
```

Photo/video on Stray exports reuse the metric cloud with widened CIs (±8% / ±3%).

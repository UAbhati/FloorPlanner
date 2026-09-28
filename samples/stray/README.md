# samples/stray/ — drop company Stray Scanner exports here

Put the **same three folders** you already give every candidate into this directory.
Keep the original folder names — do not rename.

```
samples/stray/
  single_room/
  single_scan_floor/
  single_scan_with_ceiling/
```

Each export must include: `odometry.csv`, `depth/`, `confidence/`, `rgb.mp4`.

## Run (all three tiers on one export)

```bash
source .venv/bin/activate
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar --out out/
python run.py --input samples/stray/single_scan_with_ceiling --tier photo --out out/
python run.py --input samples/stray/single_scan_with_ceiling --tier video --out out/
```

| Sample | Role | Notes from our runs |
|--------|------|---------------------|
| `single_room` | Furnished single room | ~9.9 m² `manhattan_rect`; ceiling soft-fails (furniture plane) → prior CI |
| `single_scan_floor` | Floor-heavy walk | ~27.0 m² `manhattan_rect`; ceiling ~1.83 m |
| `single_scan_with_ceiling` | Ceiling covered | ~30.5 m² `manhattan_rect`; ceiling ~1.83 m; fix-loop capture |

Photo/video on Stray exports reuse the metric cloud with widened CIs (±8% / ±3%).
No tape GT from us on these rooms — wall/ceiling centimetre gates stay “UNKNOWN vs gate” until walk-in.

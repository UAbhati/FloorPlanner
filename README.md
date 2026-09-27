# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

## Setup (macOS, ~5–15 min on a clean machine)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg colmap   # once
```

## Walk-in / Stray export (all three tiers)

Hand the unzipped Stray folder (must contain `odometry.csv`, `depth/`, `rgb.mp4`):

```bash
source .venv/bin/activate
python run.py --input /path/to/stray_export --tier lidar --out out/walkin
python run.py --input /path/to/stray_export --tier video --out out/walkin
python run.py --input /path/to/stray_export --tier photo --out out/walkin
```

Defense checklist: [docs/WALKIN_CHECKLIST.md](docs/WALKIN_CHECKLIST.md)
Capture protocol: [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md)

## Samples (smoke)

```bash
python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/
python run.py --input samples/my_room --tier photo --out out/   # needs GT or --ref-length-m/--ref-width-m
```

## Multi-room stitch (hall + bedroom)

```bash
# Opening-anchored placement (drift correction ON)
python run.py --stitch-gt my_room,bedroom --tier photo --drift-align on --out out/stitch
# Ablation without door alignment (drift OFF)
python run.py --stitch-gt my_room,bedroom --tier photo --drift-align off --out out/stitch
```

## Docs
- [docs/WALKIN_CHECKLIST.md](docs/WALKIN_CHECKLIST.md) — **30% walk-in**
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — Route 2 + device matrix
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md)
- [benchmark/REPORT.md](benchmark/REPORT.md) — gate/timing tables (regen with script)
- [benchmark/HEAD_TO_HEAD.md](benchmark/HEAD_TO_HEAD.md) — **10%** vs Polycam/Magicplan
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — **25%** fix loop
- [memory.md](memory.md) — design decisions

## Honest limits
- LiDAR: polar outline + oriented rectangle; `oriented_rect_large` = doorway bleed / multi-space.
- Ceiling soft-fails when the walk never looks up.
- Android photo/video: COLMAP often too thin → tape-scaled rectangle with tier CIs.
- Multi-room stitch: GT hall+bedroom via `--stitch-gt` (opening-aligned); not independent multi-room LiDAR.

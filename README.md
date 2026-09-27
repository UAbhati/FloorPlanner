# Indoor capture → dimensioned plan

Route 2 pipeline: Stray Scanner LiDAR + Android photo/video → schema JSON + top-down plan PNG.

## Setup (macOS, ~5 min)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# system tools (once): brew install ffmpeg colmap
```

## One command per capture

```bash
# LiDAR (Stray Scanner export folder)
python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/

# Photo (Android folder with photos/ or loose images)
python run.py --input samples/my_room --tier photo --out out/

# Video (folder containing video.mp4)
python run.py --input samples/my_room --tier video --out out/
```

Photo/video need metric scale: `--ref-length-m` / `--ref-width-m`, or rows in `benchmark/ground_truth.csv` for that folder name.

Photo/video try **COLMAP** first (scaled to the long-wall reference). If reconstruction is too thin (<200 points) or fails, they fall back to the tape/GT rectangle. Force the fallback with `--no-colmap`.

## Docs
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — what the walker installs and how they walk
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md) — requirement → artifact → status
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — fix-loop (regenerate with `python fix_loop/regenerate.py`)
- [memory.md](memory.md) — major design decisions
- [NOTES.md](NOTES.md) — debug narrative
- [schema/output.schema.json](schema/output.schema.json) — output contract

## Honest limits
- LiDAR walls use polar outline + oriented rectangle; oversized footprints are flagged.
- Ceiling fails soft when the walk never looks up.
- Photo/video on Android are thin-sensor paths (wide CIs); SfM metric reconstruction is follow-up.

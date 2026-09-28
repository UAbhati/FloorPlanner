# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

## Setup (macOS, ~5–15 min)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg colmap   # once
```

## Samples: what you get vs what you drop in

Raw capture media is **not** in this repo (size + privacy). Committed artifacts
still let you verify every reported number.

| What | In git? | Action |
|------|---------|--------|
| Benchmark JSON, plan PNGs, REPORT, H2H, fix-loop before/after | Yes | Browse / open — no download needed |
| 3 company Stray LiDAR exports | No (yours already) | Drop into `samples/stray/` — see below |
| Author phone rooms (`my_room`, `my_bedroom`, …) | No (privacy) | Not available; use committed results under `benchmark/` |

Full layout + “how to add a new capture”: **[samples/README.md](samples/README.md)**

### Drop Stray exports (tester — no renaming)

```
samples/stray/single_room/
samples/stray/single_scan_floor/
samples/stray/single_scan_with_ceiling/
```

```bash
source .venv/bin/activate
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar --out out/
```

### Or browse committed outputs (zero media)

- [`fix_loop/before/`](fix_loop/before/) vs [`fix_loop/after/`](fix_loop/after/) — wall-fix regenerable pair
- [`benchmark/h2h/`](benchmark/h2h/) — photo/video + stitch ablation JSON/PNG
- [`benchmark/REPORT.md`](benchmark/REPORT.md) · [`benchmark/HEAD_TO_HEAD.md`](benchmark/HEAD_TO_HEAD.md)
- [`benchmark/damage/`](benchmark/damage/) — staged two-class damage output

### Test any new room (phone)

```bash
mkdir -p /tmp/anyroom/photos   # drop 2–8 stills
python run.py --input /tmp/anyroom --tier photo \
  --ref-length-m <long_wall_m> --ref-width-m <short_wall_m> --out out/
```

## Walk-in (cold CLI)

Unzipped Stray folder anywhere on disk (`odometry.csv` + `depth/` + `rgb.mp4`):

```bash
source .venv/bin/activate
python run.py --input /path/to/stray_export --tier lidar --out out/walkin
python run.py --input /path/to/stray_export --tier video --out out/walkin
python run.py --input /path/to/stray_export --tier photo --out out/walkin
```

Defense checklist: [docs/WALKIN_CHECKLIST.md](docs/WALKIN_CHECKLIST.md)  
Capture protocol: [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md)

## Multi-room stitch (GT rectangles; needs author `samples/local/` or just browse committed stitch JSON)

```bash
# Opening-anchored placement (drift correction ON)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
# Ablation (drift OFF)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align off --out out/stitch
```

Committed stitch outputs: [`benchmark/h2h/stitched/`](benchmark/h2h/stitched/)

## Docs
- [samples/README.md](samples/README.md) — **drop zones, privacy, how to add a capture**
- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) — ≤6-page technical report
- [docs/WALKIN_CHECKLIST.md](docs/WALKIN_CHECKLIST.md) — 30% walk-in
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — Route 2 + device matrix
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md)
- [benchmark/REPORT.md](benchmark/REPORT.md) — gate/timing tables (`python benchmark/run_benchmark.py`)
- [benchmark/HEAD_TO_HEAD.md](benchmark/HEAD_TO_HEAD.md) — vs Magicplan
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — 25% fix loop

## Honest limits
- LiDAR: Manhattan density-peak rectangle; falls back to polar then hull; `*_large` / low_confidence = doorway bleed / multi-space.
- Ceiling soft-fails when the walk never looks up.
- Author Android photo/video: COLMAP often too thin → tape-scaled rectangle with tier CIs (disclosed).
- Multi-room stitch: GT hall+bedroom+kitchen via `--stitch-gt`; not independent multi-room LiDAR from a cold Stray walk.
- Author `samples/local/my_*` media is private; Stray media you already have — drop under `samples/stray/`.

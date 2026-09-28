# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

**Capture (non-engineer):** follow [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) literally — install the App Store tools, walk the room, hand over the export folder.
**Pipeline (this README):** clone → setup → one command per capture on a clean macOS machine (<15 min).

## Clone + setup (macOS, ~5–15 min)

**Prerequisites:** [Homebrew](https://brew.sh), Python 3.12, git.

```bash
git clone https://github.com/UAbhati/FloorPlanner.git
cd FloorPlanner

# System tools (once per machine)
brew install python@3.12 ffmpeg colmap

# Python env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Confirm the CLI:

```bash
source .venv/bin/activate
python run.py --help
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

Link RGB-only siblings for COLMAP video/photo tests:

```bash
for s in single_room single_scan_floor single_scan_with_ceiling; do
  mkdir -p "samples/stray/${s}_rgb"
  ln -sfn "../$s/rgb.mp4" "samples/stray/${s}_rgb/rgb.mp4"
done
```

```bash
source .venv/bin/activate
# LiDAR golden → out/single_room/
python run.py --input samples/stray/single_room --tier lidar
# COLMAP video → out/single_room_rgb/
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

### Or browse committed outputs (zero media)

- [`fix_loop/before/`](fix_loop/before/) vs [`fix_loop/after/`](fix_loop/after/) — wall-fix regenerable pair
- [`benchmark/h2h/`](benchmark/h2h/) — photo/video + stitch ablation JSON/PNG
- [`benchmark/REPORT.md`](benchmark/REPORT.md) · [`benchmark/HEAD_TO_HEAD.md`](benchmark/HEAD_TO_HEAD.md)
- [`benchmark/damage/`](benchmark/damage/) — staged two-class damage output

### Test any new room (phone)

```bash
mkdir -p /tmp/anyroom/photos   # drop 2–8 stills
python run.py --input /tmp/anyroom --tier photo --ref-length-m <long_wall_m>
```

## Walk-in (cold CLI)

Unzipped Stray folder anywhere on disk (`odometry.csv` + `depth/` + `rgb.mp4`):

```bash
source .venv/bin/activate
python run.py --input /path/to/stray_export --tier lidar
# RGB-only COLMAP (folder with just rgb.mp4, or samples/stray/*_rgb):
python run.py --input /path/to/stray_rgb --tier video --ref-from out/<lidar_folder>/
```

Defense: follow [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) literally (cold CLI).

## Multi-room stitch (GT rectangles; needs author `samples/local/` or just browse committed stitch JSON)

```bash
# Hub + satellites (3+ rooms). Default hub = largest floor area.
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --hub my_room --drift-align on --out out/stitch
# Ablation (opening centers not aligned)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --drift-align off --out out/stitch
```

Committed stitch outputs: [`benchmark/h2h/stitched/`](benchmark/h2h/stitched/)

## Docs
- [samples/README.md](samples/README.md) — **drop zones, privacy, how to add a capture**
- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) — ≤6-page technical report
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — Route 2 + device matrix (follow at walk-in)
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md)
- [benchmark/REPORT.md](benchmark/REPORT.md) — gate/timing tables (`python benchmark/run_benchmark.py`)
- [benchmark/HEAD_TO_HEAD.md](benchmark/HEAD_TO_HEAD.md) — vs Magicplan
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — 25% fix loop

## Honest limits
- LiDAR: Manhattan density-peak rectangle; falls back to polar then hull; `*_large` / low_confidence = doorway bleed / multi-space.
- Ceiling soft-fails when the walk never looks up.
- Photo/video: COLMAP SfM (default 100 frames; long walks auto-raise to ≤1.0s spacing). Fails honestly if reconstruction is thin — no silent GT-rectangle substitute (`--no-colmap` is ablation-only). Scale via `--ref-from` (LiDAR golden) or `--ref-length-m`.
- Stray RGB vs LiDAR golden (scaled): short-wall within ±5% on single_room / floor / ceiling with current sparse fit (PCA-up + polar aspect pick).
- Multi-room stitch: GT hub + satellites via `--stitch-gt` (not independent multi-room LiDAR from a cold Stray walk).
- Author `samples/local/my_*` media is private; Stray media you already have — drop under `samples/stray/`.

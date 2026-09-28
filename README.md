# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

**Capture (non-engineer):** follow [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) literally — install the App Store tools, walk the room, hand over the export folder.
**Pipeline (this README):** clone → setup → point `--input` at any capture folder.

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

```bash
source .venv/bin/activate
python run.py --help
```

## Capture folder layout

`--input` is any folder (relative or absolute). Tier selects which files are used.
You do **not** need this repo’s `samples/` tree — only the files below.

| Tier | Put in the folder | Example |
|------|-------------------|---------|
| `lidar` | Stray export: `odometry.csv` + `depth/` (+ `confidence/`, `rgb.mp4`) | unzipped Stray share |
| `photo` | `photos/*.jpg` **or** loose stills in the folder root | 2–8 overlapping phone shots |
| `video` | one of `video.mp4`, `rgb.mp4`, or any `*.mp4` / `*.mov` | phone walk or Stray RGB |

```
<capture_folder>/                 # --input path (relative or absolute)
  # LiDAR (Stray) — need all of these for --tier lidar
  odometry.csv
  depth/                          # depth frames
  confidence/                     # optional but usual
  rgb.mp4                         # optional for LiDAR; required if you also run video

  # Phone photo — either layout works for --tier photo
  photos/*.jpg
  # …or stills directly in <capture_folder>/

  # Phone / RGB video — for --tier video (or photo if no stills)
  video.mp4                       # or rgb.mp4 / other *.mp4
```

Default output: `out/<folder_name>/` (override with `--out`).

## Run (general)

```bash
source .venv/bin/activate

# LiDAR
python run.py --input <capture_folder> --tier lidar

# Photo (needs metric scale: tape long wall, or --ref-from a LiDAR run)
python run.py --input <capture_folder> --tier photo --ref-length-m <long_wall_m>

# Video / COLMAP (same scale options)
python run.py --input <capture_folder> --tier video --ref-length-m <long_wall_m>

# Scale photo/video from a prior LiDAR JSON (or its out/ dir)
python run.py --input <rgb_or_phone_folder> --tier video --ref-from <lidar_out_dir_or_json>

# Compare two outputs (e.g. LiDAR golden vs COLMAP)
python run.py --compare <out_a/> <out_b/>
```

Optional: `--colmap-frames 100` (default; long videos auto-raise), `--out <dir>`.

### Walk-in examples

```bash
# Unzipped Stray export anywhere
python run.py --input ./stray_export --tier lidar

# RGB-only COLMAP scaled from that LiDAR run
python run.py --input ./stray_export --tier video --ref-from out/stray_export/

# Phone stills with a taped long wall
mkdir -p ./anyroom/photos   # drop 2–8 stills into photos/
python run.py --input ./anyroom --tier photo --ref-length-m 3.5
```

Defense: follow [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) literally (cold CLI).

## What’s in git vs what you drop in

Raw capture media is **not** in this repo (size + privacy). Committed artifacts
still let you verify every reported number.

| What | In git? | Action |
|------|---------|--------|
| Benchmark JSON, plan PNGs, REPORT, H2H, fix-loop before/after | Yes | Browse / open — no download needed |
| Company Stray LiDAR exports | No (testers already have them) | Put each export in any folder; or under `samples/stray/<name>/` |
| Author phone rooms (`my_room`, …) | No (privacy) | Use committed results under `benchmark/` |

More detail: **[samples/README.md](samples/README.md)**

### Optional: company Stray drop-in names

If you use the shared tester names:

```
samples/stray/single_room/
samples/stray/single_scan_floor/
samples/stray/single_scan_with_ceiling/
```

```bash
python run.py --input samples/stray/single_room --tier lidar
# RGB-only sibling (copy or symlink rgb.mp4 into a second folder):
mkdir -p samples/stray/single_room_rgb
ln -sfn ../single_room/rgb.mp4 samples/stray/single_room_rgb/rgb.mp4
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

### Browse committed outputs (zero media)

- [`fix_loop/before/`](fix_loop/before/) vs [`fix_loop/after/`](fix_loop/after/) — wall-fix regenerable pair
- [`benchmark/h2h/`](benchmark/h2h/) — photo/video + stitch ablation JSON/PNG
- [`benchmark/REPORT.md`](benchmark/REPORT.md) · [`benchmark/HEAD_TO_HEAD.md`](benchmark/HEAD_TO_HEAD.md)
- [`benchmark/damage/`](benchmark/damage/) — staged two-class damage output

## Multi-room stitch (GT rectangles)

Uses committed `benchmark/ground_truth.csv` (no raw media required):

```bash
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --hub my_room --drift-align on --out out/stitch
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --drift-align off --out out/stitch
```

Committed stitch outputs: [`benchmark/h2h/stitched/`](benchmark/h2h/stitched/)

## Docs
- [samples/README.md](samples/README.md) — capture layout, privacy, adding a room
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
- Author `samples/local/my_*` media is private; drop your own captures in any folder and pass `--input`.

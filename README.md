# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

**Capture (non-engineer):** follow [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) literally — install the App Store tools, walk the room, hand over the export folder.
**Pipeline (this README):** clone → setup → point `--input` at any capture folder.

## Clone + setup (macOS, ~5–15 min)

You’ll need [Homebrew](https://brew.sh), Python 3.12, and git.

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

`--input` is any folder (relative or absolute). Tier picks which files get used.
You don’t need this repo’s `samples/` tree — just the files below.

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

I left raw capture media out of the repo — too big, and my own rooms are private.
You can still check every number from what’s committed under `benchmark/` and `fix_loop/`.

- **Committed outputs** (JSON, plan PNGs, REPORT, H2H, fix-loop before/after) — already in git; just open them.
- **Company Stray LiDAR exports** — not in git (testers already have them). Drop each export in any folder, or under `samples/stray/<name>/`.
- **My phone rooms** (`my_room`, …) — I keep those under [`samples/local/`](samples/local/) for my own testing. Reviewers don’t need that folder; use the committed results in `benchmark/` instead.

More detail: **[samples/README.md](samples/README.md)**

### Optional: company Stray drop-in names

If you’re using the shared tester names:

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

- [`fix_loop/before/`](fix_loop/before/) vs [`fix_loop/after/`](fix_loop/after/) — wall-fix before/after pair
- [`benchmark/h2h/`](benchmark/h2h/) — photo/video + stitch ablation JSON/PNG
- [`benchmark/REPORT.md`](benchmark/REPORT.md) · [`benchmark/HEAD_TO_HEAD.md`](benchmark/HEAD_TO_HEAD.md)
- [`benchmark/damage/`](benchmark/damage/) — staged two-class damage output

## Multi-room stitch

I stitch from room ids in `benchmark/ground_truth.csv` (tape dims for the demo —
not a stand-in for live SfM):

```bash
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --hub my_room --drift-align on --out out/stitch
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo \
  --drift-align off --out out/stitch
```

Committed stitch outputs: [`benchmark/h2h/stitched/`](benchmark/h2h/stitched/)

## Docs
- [samples/README.md](samples/README.md) — capture layout, privacy, adding a room
- [samples/local/README.md](samples/local/README.md) — my local captures (reviewers don’t need this)
- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) — ≤6-page technical report
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — Route 2 + device matrix (follow at walk-in)
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md)
- [benchmark/REPORT.md](benchmark/REPORT.md) — gate/timing tables (`python benchmark/run_benchmark.py`)
- [benchmark/HEAD_TO_HEAD.md](benchmark/HEAD_TO_HEAD.md) — vs Magicplan
- [benchmark/ground_truth.csv](benchmark/ground_truth.csv) — tape GT for validation / testing only
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — 25% fix loop

## Honest limits
- Ceiling soft-fails when the walk never looks up.
- Photo/video COLMAP fails honestly if reconstruction is thin; needs `--ref-length-m` or `--ref-from` for scale.
- I don’t have an iPhone — LiDAR was validated on company Stray exports, not my own Pro captures; photo/video/H2H are from my Android phone.

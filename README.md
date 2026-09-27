# Indoor capture → dimensioned plan

Route 2 pipeline: **Stray Scanner** (LiDAR) + phone photo/video → schema JSON + top-down plan.

## Fastest ways to see this work (no setup, or ~2 min)

**Note on samples:** `samples/` is not in this repo — the 3 Stray LiDAR captures are yours (given to every candidate, not ours to redistribute), and `my_room`/`my_bedroom`/`my_kitchen` are photos/video of the author's own home, kept private. See [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md) for the full disclosure. What follows still gets you to a live, working pipeline in minutes.

1. **Zero setup — browse committed outputs.** Every number in this repo is backed by a committed JSON + rendered plan PNG, not just prose:
   - [`fix_loop/before/`](fix_loop/before/) vs [`fix_loop/after/`](fix_loop/after/) — hull-baseline vs the shipped Manhattan wall-detection fix, same two Stray captures
   - [`benchmark/h2h/our_room_a|b|c/`](benchmark/h2h/) — our photo **and video** tier output per room (hall/bedroom/kitchen)
   - [`benchmark/h2h/stitched/`](benchmark/h2h/stitched/) — the 3-room stitch, **both** `drift_on` and `drift_off` (the ablation the spec scores)
   - [`benchmark/REPORT.md`](benchmark/REPORT.md), [`benchmark/HEAD_TO_HEAD.md`](benchmark/HEAD_TO_HEAD.md) — the full tables these files back

2. **~2 min, live run, zero privacy concern — your own Stray samples.** Drop the same 3 folders you already gave every candidate (`single_room/`, `single_scan_floor/`, `single_scan_with_ceiling/`) into `samples/`, then:
   ```bash
   source .venv/bin/activate
   python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/
   ```
   This is the actual LiDAR code path — the same one that runs cold at the walk-in test.

3. **~1 min, live run, any room, zero data needed from us.** The photo tier's whole promise is "any picture in, results out" — prove it with your own phone:
   ```bash
   mkdir -p /tmp/anyroom && # drop 2-8 phone photos of any room in there
   python run.py --input /tmp/anyroom --tier photo --ref-length-m <tape a wall> --ref-width-m <tape the other> --out out/
   ```

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

## Multi-room stitch (hall + bedroom + kitchen, 3 rooms + connector)

```bash
# Opening-anchored placement (drift correction ON)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
# Ablation without door alignment (drift OFF)
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align off --out out/stitch
```

## Docs
- [TECHNICAL_REPORT.md](TECHNICAL_REPORT.md) — **≤6-page technical report** (architecture, tiers, drift, fix loop)
- [docs/WALKIN_CHECKLIST.md](docs/WALKIN_CHECKLIST.md) — **30% walk-in**
- [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) — Route 2 + device matrix
- [docs/COMPLIANCE_MATRIX.md](docs/COMPLIANCE_MATRIX.md)
- [benchmark/REPORT.md](benchmark/REPORT.md) — gate/timing tables (regen with script)
- [benchmark/HEAD_TO_HEAD.md](benchmark/HEAD_TO_HEAD.md) — **10%** vs Polycam/Magicplan
- [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md) — **25%** fix loop

## Honest limits
- LiDAR: Manhattan density-peak rectangle (Hough angle + per-axis wall-position peak), falls back to polar outline then hull; `*_large` tag = doorway bleed / multi-space.
- Ceiling soft-fails when the walk never looks up.
- Android photo/video: COLMAP often too thin → tape-scaled rectangle with tier CIs.
- Multi-room stitch: GT hall+`my_bedroom`+`my_kitchen` (3 rooms + connector) via `--stitch-gt` (opening-aligned, hall as star center); not independent multi-room LiDAR.

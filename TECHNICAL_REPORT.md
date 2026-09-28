# Technical Report — Indoor Capture → Dimensioned Plan

**Route 2 (stock capture) · Cozmo AI case study · September 2026**
**Entrypoint:** `run.py` · **Schema:** `schema/output.schema.json` · **Benchmark regen:** `python benchmark/run_benchmark.py`
**Length target:** ≤6 pages.

---

## 1. Problem and capture route

We produce a dimensioned per-room plan (walls, openings, ceiling height, floor area), a stitched multi-room plan with correct adjacency, rule-based damage/scope lines, and a confidence interval on every measurement — from **one CLI command per capture** — for three mandatory input tiers: **photo**, **video**, and **LiDAR**.

**Route 2 (stock tools), not a custom iOS app.** Capture uses App Store / native camera only:

| Tool | Role |
|------|------|
| [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) | LiDAR depth, poses, intrinsics → export folder |
| Native Camera | Per-room photo folders and handheld walkthrough video |

Protocol (install, walk, avoid, **handoff**, device matrix): `docs/CAPTURE_PROTOCOL.md`. Defense follows that page literally.

**Hardware honesty.** I do **not** own an iPhone Pro. LiDAR is validated on **company Stray exports**. Photo/video and Magicplan H2H are from my **Android** phone. Assignment target hardware remains iPhone 15+ / Pro for walk-in; the pipeline accepts those exports cold.

```bash
python run.py --input <capture_folder> --tier lidar
python run.py --input <capture_folder> --tier video --ref-from <lidar_out_dir/>
python run.py --input <capture_folder> --tier photo --ref-length-m <long_wall_m>
# Live stitch from prior-run JSONs:
python run.py --stitch-inputs out/hall,out/bedroom,out/kitchen --tier photo --hub <id> --drift-align on
# Tape-rectangle stitch demo / drift ablation:
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
python run.py --compare <out_a/> <out_b/>
```

---

## 2. Architecture

```
capture_io/           Stray loader; phone photo/video resolve + ffmpeg frames
reconstruction/
  pointcloud.py       Depth + odometry → metric cloud
  planes.py           Floor / ceiling RANSAC
  wall_detection.py   Manhattan density-peak → polar → hull
  room_polygon.py     Walls, openings, floor area
  media_layout.py     GT CSV load for --stitch-gt / eval only
  sfm_colmap.py       COLMAP SfM + metric scale
  stitch.py           stitch_from_rooms (live) + stitch_from_gt (tape demo)
  damage.py           water_stain + surface_crack + concealed_behind_opening
  render.py / validation.py
run.py                Tier dispatch, --stitch-inputs / --stitch-gt, schema emit
benchmark/            REPORT, H2H, damage, COLMAP validation, GT CSV
fix_loop/            Declaration + regenerable before/after
```

**LiDAR.** Stray cloud → floor RANSAC → ceiling (≥ ~1.8 m band; reject &lt; 1.7 m furniture) → wall band → **Manhattan density-peak rectangle** (fallback polar, then hull) → openings → JSON + plan. Ceiling soft-fail uses residential prior CI + note.

**Photo / video.** Always **COLMAP SfM**. Scale **only** via `--ref-length-m` or `--ref-from` — **no silent `ground_truth.csv` lookup by folder name**. Thin reconstruction **fails closed**. Stray `*_rgb` siblings pass short-wall ±5% vs LiDAR golden (`benchmark/colmap_validation/`). Assignment allows 2–8 stills; SfM needs ≥3 overlapping views (exactly 2 fails closed); prefer ~8.

**Damage.** Rule-based on photo/video frames. LiDAR emits empty `damage_regions` / `scope_line_items` (schema-valid). Evidence: `benchmark/damage/`.

---

## 3. Tier design and device matrix

| Tier | Assignment target | Also tested | Metric source | Wall CI |
|------|-------------------|-------------|---------------|---------|
| LiDAR | iPhone 15 Pro + Stray | Company Stray exports | Depth + poses | Residuals / flags |
| Video | iPhone 15+ | Android; Stray `rgb.mp4` | COLMAP + ref | ±3% |
| Photo | iPhone 15+ | Android stills | COLMAP + ref | ±8% |

\*Timings in `benchmark/REPORT.md`.

**Calibration.** Photo/video CIs stay at tier width even when COLMAP succeeds. GT CSV is for `--stitch-gt` / offline eval — not production scale.

**Gates vs Stray.** No tape GT on company rooms → opening ≤2 cm / ceiling ≤1.5 cm are **UNKNOWN vs gate**. Walk-in uses graders’ laser.

---

## 4. Drift handling and multi-room stitch

**Live path:** `--stitch-inputs` loads prior-run JSON/out dirs → `stitch_from_rooms` (hub + satellites, opening match or south-wall fallback). Drift on/off via `--drift-align`.

**Demo / ablation path:** `--stitch-gt` builds tape rectangles from `benchmark/ground_truth.csv` (hall hub + bedroom + kitchen). Footprint **20.138 m²** on/off; method `plane_anchored_correction` vs `poses_as_is`.

| Setting | Method | Footprint |
|---------|--------|-----------|
| on | `plane_anchored_correction` | **20.138 m²** |
| off | `poses_as_is` | **20.138 m²** |

Smoke-tested live COLMAP → `--stitch-inputs` on two Stray RGB rooms (unrelated spaces — CLI proof, not a property claim). Property-grade live stitch needs COLMAP success on connected phone rooms (still often thin).

**Why opening hinges, not pose-graph loop closure.** No continuous multi-room Pro walk on my side. Drift story = door-center alignment in the floor plane.

---

## 5. Error budget and calibration

### 5.1 Budget

| Quantity | Photo | Video | LiDAR |
|----------|-------|-------|-------|
| Wall | ±8% | ±3% | Residual / low_confidence; no cm claim without GT |
| Ceiling | ±8% or prior | ±3% or prior | Plane σ or prior 1.5–3.5 m |
| Openings | Inherited | Inherited | Gap heuristic; ≤2 cm not claimed on Stray |

### 5.2 Benchmark composition

| Capture | Tiers | Role |
|---------|-------|------|
| Stray `single_*` | lidar + video (`*_rgb`) | Walk-in-shaped LiDAR; COLMAP vs golden |
| `my_*` phone rooms | photo / video | Live COLMAP + explicit tape refs; H2H under `benchmark/h2h/` |
| `my_bedroom_repeat` | photo / video | Live COLMAP repeat — geometry **not** identical (gate FAIL; disclosed) |

**Gap (no Pro):** same physical room with independent photo + video + LiDAR not available.

### 5.3 Stray COLMAP vs LiDAR golden

| Sample | Short-wall err | Verdict |
|--------|----------------|---------|
| `single_room` | **2.8%** | PASS ±5% |
| `single_scan_floor` | **1.5%** | PASS |
| `single_scan_with_ceiling` | **1.8%** | PASS |

### 5.4 Head-to-head — Part 3 gap disclosed

Brief asks **LiDAR vs consumer app** on the same rooms. **Delivered:** Magicplan Android (typed plan) vs our **photo** tier on hall + bedroom (+ kitchen) — **13/13** beat/tie shared dims (`benchmark/HEAD_TO_HEAD.md`). Useful engineering evidence; **not** Part 3. Cannot complete LiDAR↔app without a Pro.

### 5.5 Damage

`water_stain` / `surface_crack` / `concealed_moisture_risk` on staged hall photos (`benchmark/damage/`). Rule-based, not ML.

---

## 6. Fix-loop (25%)

**Before:** hull on `single_scan_with_ceiling` → **~115 m²**, 8-vertex junk.
**Cause:** filled wall-band (clutter + doorway bleed).
**After:** Manhattan density-peak → **~30.5 m²**, 4 walls, `low_confidence=False`.
Bundle: `fix_loop/DECLARATION.md`, `before/`, `after/`, `python fix_loop/regenerate.py`.

---

## 7. Known failure modes

1. Doorway bleed / multi-space — density-peak helps; no Stray tape for cm gates.
2. Eye-level-only LiDAR — ceiling soft-fail.
3. Thin COLMAP — fail closed (≥3 views; prefer 8).
4. `--stitch-gt` = tape composition demo; prefer `--stitch-inputs` when live rooms exist.
5. Repeatability — live COLMAP on two walks with shared `--ref-length-m`; walls **disagree** (gate FAIL). Not the old tape-rectangle identical pair.
6. LiDAR damage lists empty; staged damage evidence is photo (`benchmark/damage/`; live 5-still SfM thin).
7. **No personal Pro** → Part 3 LiDAR H2H and same-room×3 tiers incomplete.
8. Phone COLMAP can clear SfM yet miss ±8%/±3% short-wall vs tape (honest FAIL in REPORT).
9. Walk-in — graders’ laser is GT; cold CLI on their capture.

---

## 8. Reproduction / submission

| Item | Location |
|------|----------|
| Setup &lt;15 min (macOS) | `README.md` |
| Protocol + handoff | `docs/CAPTURE_PROTOCOL.md` |
| Compliance | `docs/COMPLIANCE_MATRIX.md` |
| Benchmark | `benchmark/REPORT.md` |
| Fix loop | `fix_loop/` |

Cold walk-in: drop Stray/phone folder → `--tier lidar|photo|video` (+ `--ref-length-m` for phone). Cached JSON/PNG under `benchmark/` replay reported tables; live path is what defense runs.

**Defense (tools closed).** (1) Manhattan vs polar/hull. (2) `--stitch-inputs` live + `--stitch-gt` ablation disclosed. (3) Scale only CLI refs; live phone COLMAP may miss tape ±8%/±3% — REPORT fails honestly. (4) Stray RGB ±5% PASS. (5) Repeatability live SfM disagrees across walks. (6) Damage photo committed evidence. (7) No Pro → Part 3 / same-room×3 gaps owned; walk-in still cold on graders’ device.

---

## 9. Summary

Route 2 pipeline with honest CIs, regenerable fix-loop, COLMAP fail-closed, Stray RGB validated against LiDAR, live `--stitch-inputs` plus GT drift ablation, photo↔Magicplan H2H. **Main residual risks:** centimetre LiDAR on the unseen walk-in room, and brief rows that require a personal Pro (Part 3 LiDAR H2H, same-room×3 tiers) which I cannot close without that hardware.

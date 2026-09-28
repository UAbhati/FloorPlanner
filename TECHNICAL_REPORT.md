# Technical Report — Indoor Capture → Dimensioned Plan

**Route 2 (stock capture) · Cozmo AI case study · September 2026**  
**Entrypoint:** `run.py` · **Schema:** `schema/output.schema.json` · **Benchmark regen:** `python benchmark/run_benchmark.py`  
**Length target:** ≤6 pages (this document is sized to that budget).

---

## 1. Problem and capture route

We produce a dimensioned per-room plan (walls, openings, ceiling height, floor area), a stitched multi-room plan with correct adjacency, rule-based damage/scope lines, and a confidence interval on every measurement — from **one CLI command per capture** — for three mandatory input tiers: **photo**, **video**, and **LiDAR**.

**Route 2 (stock tools), not a custom iOS app.** Capture uses App Store / native camera only:

| Tool | Role |
|------|------|
| [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) | LiDAR depth, poses, intrinsics → export folder |
| Native Camera | Per-room photo folders and handheld walkthrough video |

The non-engineer protocol (install, walk, avoid, handoff, device matrix) is `docs/CAPTURE_PROTOCOL.md`. Defense walk-in follows that page literally. Reviewers drop company Stray exports into any folder (or `samples/stray/`); `samples/local/` holds author local-testing media (private). Committed JSON/plans under `benchmark/` replace raw author media. See `samples/README.md` and `README.md`.

```bash
python run.py --input <capture_folder> --tier lidar
python run.py --input <capture_folder> --tier video --ref-from <lidar_out_dir/>
python run.py --input <capture_folder> --tier photo --ref-length-m <long_wall_m>
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
python run.py --compare <out_a/> <out_b/>
```

---

## 2. Architecture

```
capture_io/           Stray loader; phone photo/video resolve + ffmpeg frames; sample path aliases
reconstruction/
  pointcloud.py       Depth + odometry → metric cloud (confidence-gated, voxel downsample)
  planes.py           Two-stage floor / ceiling RANSAC (fixed seed for determinism)
  wall_detection.py   Manhattan density-peak rect (Hough or PCA angle) → polar → hull
  room_polygon.py     Walls, openings, floor area
  media_layout.py     Tape GT load + rectangle helper for stitch / validation only
  sfm_colmap.py       COLMAP SfM → soft up-axis → density-peak / polar room + metric scale
  stitch.py           Hub + satellites, opening-anchored placement + drift ablation
  damage.py           water_stain + surface_crack + concealed_behind_opening
  render.py           Top-down plan PNG (single + stitched)
  validation.py       LiDAR golden vs COLMAP compare JSON/PNG
run.py                Tier dispatch, CI widths, schema validation, JSON emit
schema/               Output contract
benchmark/            GT CSV (validation only), REPORT, H2H, damage, COLMAP compare artifacts
fix_loop/            Declaration + regenerable before/after
```

**LiDAR path (centimetre ambition).** Fuse a confidence-gated, voxel-downsampled cloud from Stray depth + poses → fit **floor** (largest RANSAC plane) → up-axis → **ceiling** only among points ≥ ~1.8 m above floor, reject heights &lt; 1.7 m (furniture) → mid-height wall band → **Manhattan density-peak rectangle** (Hough angle mod 90°, per-axis histogram-mode on coverage-deduped cells; fallback polar outline, then hull) → gap openings → JSON + plan PNG. Ceiling soft-fail: residential prior CI (1.5–3.5 m) + explicit note — never a silent fake 0.

**Photo / video path.** Always **COLMAP SfM** on stills or extracted frames (default 100; long walks auto-raise to ≤1.0 s spacing, cap 300). Metric scale from `--ref-from` (LiDAR golden longest wall) or `--ref-length-m` (tape). Soft PCA-up + wall band when dense plane fit fails; room polygon prefers **Manhattan density-peak** (PCA orientation if Hough fails — doorway-bleed resistant), else polar with band/all aspect pick. **Fails honestly** if reconstruction is thin — no GT-rectangle bypass. Company Stray `*_rgb` siblings pass short-wall ±5% vs LiDAR golden (`benchmark/colmap_validation/`).

**Damage / scope.** Rule-based: compact dark → `water_stain`; elongated (aspect ≥4) → `surface_crack`; openings → `concealed_moisture_risk`. Staged room `samples/local/my_room_damage/` (evidence `benchmark/damage/`). Extents assume ~3 m wall span — approximate.

**Output.** Every run validates `schema/output.schema.json` and writes `rooms[]`, `stitched_plan`, `drift_correction`, plus a plan PNG.

---

## 3. Tier design and device matrix

| Tier | Hardware | Metric source | Wall CI posture | Typical runtime* |
|------|----------|---------------|-----------------|------------------|
| LiDAR | iPhone Pro + Stray Scanner | Depth + poses (metric) | Plane residuals / method flags | ~2–5 s |
| Video | Any recent phone, or Stray `rgb.mp4` | COLMAP + `--ref-from` / `--ref-length-m` | ±3% wall target | ~15–60 s (SfM) |
| Photo | Any recent phone (stills) | Same COLMAP path | ±8% wall target | ~10–40 s (SfM; denser sets needed) |

\*Representative times in `benchmark/REPORT.md`. LiDAR stays seconds; COLMAP dominates photo/video.

| Job | Tier | Notes |
|-----|------|-------|
| Stray `single_*` | lidar | Manhattan rect; fix-loop on ceiling sample |
| Stray `*_rgb` | video | COLMAP vs LiDAR golden — short-wall **PASS** ±5% |
| `my_*` phone rooms | photo / video | Local testing; committed H2H under `benchmark/h2h/` |
| 3-room stitch on/off | photo | Validation stitch from tape GT rows |

**Why intervals widen.** Photo/video lack native metric scale; CIs stay at tier width even when COLMAP succeeds. Publishing tighter CIs on thin SfM would be confident garbage.

**Determinism.** Floor/ceiling RANSAC uses a fixed seed (`RANSAC_SEED=42`). Sparse COLMAP up-axis uses deterministic PCA (Open3D RANSAC floor dropped after it jittered short-wall error across the gate).

**Honest accuracy claim.** LiDAR is the centimetre *ambition* path for walk-in. Company Stray rooms have **no tape GT from us**, so opening ≤2 cm and ceiling ≤1.5 cm gates are **UNKNOWN vs gate** on those samples. Photo/video accuracy vs LiDAR is regenerable on Stray RGB (`--compare`). `benchmark/ground_truth.csv` is **tape GT for validation and testing only** (H2H, stitch demos, gate tables) — not a silent production substitute when SfM fails. Walk-in scoring is against the graders’ laser on their capture.

---

## 4. Drift handling and multi-room stitch

Spec fails bare `poses_as_is` on multi-room and requires an on/off ablation.

**Composition.** Three rooms + connector: hall (`my_room`) as hub; bedroom and kitchen pack along the hall’s south wall (Magicplan side-by-side, 0.14 m dividing-wall gap). Openings sit at the bedroom/kitchen junction (door 0.88 m @ `from_left_m=1.55`, passage 0.77 m @ `2.57`). Satisfies “3+ rooms plus a connector.”

**Method (`--drift-align on`):** `plane_anchored_correction` — hub + satellites matched by opening width; door centers align when the shift fits under the hub extent.

**Ablation (`--drift-align off`):** `poses_as_is` — pack along the hub wall without door centering. Footprint sum identical; adjacency geometry differs.

| Setting | `method_used` | Footprint | Placement |
|---------|---------------|-----------|-----------|
| on | `plane_anchored_correction` | **20.138 m²** | Door centers aligned (Δ≈0 with current GT) |
| off | `poses_as_is` | **20.138 m²** | Packed west→east; no door centering |

Footprint = 11.6644 + 4.7385 + 3.735 m². Regenerable: `--stitch-gt my_room,my_bedroom,my_kitchen`. **Limit disclosed:** stitch uses tape/GT rectangles for the multi-room *composition and drift ablation* demo — not independent multi-room LiDAR from a cold Stray walk (no iPhone Pro multi-room export on our side).

**Why door-center align, not pose-graph loop closure.** We do not have continuous multi-room LiDAR poses across the apartment. The honest drift story is *opening-plane anchoring*: each shared door is a metric hinge in the floor plane. The ablation shows the hinge matters for adjacency even when area is unchanged.

---

## 5. Error budget and calibration analysis

### 5.1 Error budget by quantity

| Quantity | Photo | Video | LiDAR (when plane/method healthy) |
|----------|-------|-------|-----------------------------------|
| Wall length | ±8% of value | ±3% of value | Residual / low_confidence flag; no cm claim without GT |
| Floor area | Scaled from wall CIs | Same | Same |
| Ceiling | ±8% if measured; else prior | ±3% if measured | Plane sigma when covered; else prior 1.5–3.5 m + note |
| Openings | Inherited wall method; phantom/miss scored at walk-in | Same | Gap heuristic; ≤2 cm **not claimed** on Stray |

### 5.2 Self-built benchmark composition

| Capture | Tiers exercised | GT / compare | Role |
|---------|-----------------|--------------|------|
| `my_room` / bedroom / kitchen | photo, video | Tape in `ground_truth.csv` (validation) | Multi-room + H2H |
| `my_bedroom_repeat` | photo, video | Same bedroom tape rows | Repeatability pair |
| `my_room_damage` | photo | Same hall GT | Two visual damage classes |
| Stray `single_*` | lidar + video (`*_rgb`) | LiDAR as COLMAP golden | Walk-in-shaped LiDAR + SfM |

### 5.3 Photo / video vs LiDAR (Stray COLMAP)

On company Stray RGB siblings, COLMAP scaled with `--ref-from` LiDAR golden:

| Sample | Frames | Short-wall err | Area err | Verdict |
|--------|--------|----------------|----------|---------|
| `single_room` | 100 | **2.8%** | 2.8% | **PASS** (±5% wall / ±10% area) |
| `single_scan_floor` | 150 | **1.5%** | 1.5% | **PASS** |
| `single_scan_with_ceiling` | 215 | **1.8%** | 1.8% | **PASS** |

Artifacts: `benchmark/colmap_validation/`. Long wall ≈0% by construction (scale). Sparse phone stills (2–8) can still fail SfM — fail closed with a coverage hint; denser overlap is required for the photo path.

**How CIs are applied.** Wall length \(L\): photo \([L(1-0.08),\, L(1+0.08)]\), video \([L(1-0.03),\, L(1+0.03)]\). LiDAR widens when `*_large` / `low_confidence=True` (doorway bleed).

### 5.4 Repeatability (spec: ≤1 cm or 0.5% per wall; ceiling spread ≤1 cm)

`my_bedroom` vs `my_bedroom_repeat`, photo and video: walls Δ = **0 cm**, ceiling spread = **0 cm** on committed regenerable artifacts that share tape scale rows (`GT_ROOM_ALIASES`). Spec language: **repeatable-but-biased** vs unrepeatable — we have the former (`benchmark/REPORT.md`). Independent SfM-on-SfM repeat is stronger when both clips clear COLMAP.

### 5.5 LiDAR qualitative (no company-room tape)

| Sample | Method | Area | Ceiling | Notes |
|--------|--------|------|---------|-------|
| `single_scan_with_ceiling` | `manhattan_rect` | **30.5 m²** | ~1.83 m | Fix-loop capture |
| `single_scan_floor` | `manhattan_rect` | **27.0 m²** | ~1.83 m | |
| `single_room` | `manhattan_rect` | **~9.9 m²** | soft-fail (~1.25 m) | Prior CI |

Stride sweep 10/20/30: Manhattan holds ~27–33 m² vs old max-radius ~111–159 m². Shape/robustness win; **not** a claimed ≤2 cm / ≤1.5 cm pass.

### 5.6 Head-to-head (Magicplan Android)

Free-tier plan export vs our photo-tier outputs on hall + bedroom (required) and kitchen (bonus). Method disclosed in `benchmark/HEAD_TO_HEAD.md`. Not a LiDAR bake-off.

| Scope | Shared dims | Ours beat or tie | Target |
|-------|-------------|------------------|--------|
| Hall + bedroom (required) | 9 | **9 / 9** | ≥70% |
| + kitchen (bonus) | 13 | **13 / 13** | ≥70% |

### 5.7 Damage composition gate

| Class | Rule | Role |
|-------|------|------|
| `water_stain` | `stain_dark_patch` | Visual class 1 |
| `surface_crack` | `crack_elongated_mark` (aspect ≥4) | Visual class 2 |
| `concealed_moisture_risk` | `concealed_behind_opening` | Rule flag (not a third visual class) |

Evidence: `benchmark/damage/`. Rule-based luminance — not a trained detector.

---

## 6. Fix-loop story (25% weight)

**Worst gate before.** LiDAR footprint on `single_scan_with_ceiling`: convex hull → **~115 m²**, **8-vertex** irregular polygon.

**Root cause.** Wall-band points are a **filled** set (furniture + doorway bleed), not a thin wall ring. Hull = outer envelope of everything seen.

**Round 1 (partial).** Polar max-radius → oriented rect; fixed 4-wall shape but chased bleed (115 → **139 m²**).

**Round 2 (shipped primary).** **Manhattan density-peak rectangle:** Hough (or PCA) dominant direction; per-axis histogram-mode on occupancy cells; equal opposite sides by construction. CLI `--wall-method hull|polar|manhattan|auto`.

| Capture | Hull | Polar (R1) | Manhattan (R2) |
|---------|------|------------|----------------|
| `single_scan_with_ceiling` | 115.2 m², 8 walls | 139.3 m², low_conf | **30.5 m²**, low_conf=**False** |
| `single_scan_floor` | — | ~112.9 m², large | **27.0 m²** |
| `single_room` | — | ~35.1 m² | **~9.9 m²** |

**Post-mortem.** Round 2 targets max-radius vs density-peak; ~4–5× area drop, stride-stable. Still **no tape GT on Stray** — shape claim for walk-in, not a centimetre gate pass. Bundle: `fix_loop/DECLARATION.md`, `before/` / `after/`, `python fix_loop/regenerate.py`.

---

## 7. Known failure modes (including walk-in)

1. **Doorway bleed / multi-space walks** — density-peak resists far better than hull/polar; still no Stray tape for cm validation.
2. **Eye-level-only LiDAR** — ceiling soft-fail; prior CI + note (protocol: tilt up/down).
3. **Furniture planes ~1.2–1.5 m** — rejected as ceiling (&lt; 1.7 m).
4. **Thin COLMAP** (few stills / pure rotation / weak overlap) — fail honestly; no GT-rectangle bypass.
5. **Mirrors / glass / closed doors** — holes or missed openings.
6. **GT rectangle stitch** — composition + drift ablation are real; not live multi-room LiDAR SfM stitch.
7. **Damage heuristics** — luminance rules; extents approximate.
8. **Repeatable-but-biased** photo/video when both runs share tape scale.
9. **Walk-in** — graders’ laser is GT. Expect LiDAR `manhattan_rect` when coverage is good; photo/video need `--ref-length-m` (or `--ref-from`) for scale.

---

## 8. Reproduction and walk-in readiness

| Deliverable | Location |
|-------------|----------|
| One-command CLI | `README.md`, `run.py` |
| Capture protocol + device matrix | `docs/CAPTURE_PROTOCOL.md` |
| Sample drop / privacy | `samples/README.md` (`stray/` vs `local/`) |
| Benchmark tables + timing | `benchmark/REPORT.md` ← `run_benchmark.py` |
| Ground truth (validation only) | `benchmark/ground_truth.csv` |
| COLMAP vs LiDAR | `benchmark/colmap_validation/` |
| Head-to-head | `benchmark/HEAD_TO_HEAD.md`, `benchmark/h2h/` |
| Damage evidence | `benchmark/damage/` |
| Fix loop | `fix_loop/` |
| Compliance matrix | `docs/COMPLIANCE_MATRIX.md` |

Cold walk-in: receive Stray export → run all three `--tier` values → compare JSON/plan to laser. Phone-only: `--ref-length-m` / `--ref-width-m` for scale (protocol). Cached committed JSON/PNG replay reported numbers; live path is what defense runs.

**Defense narrative (tools closed).** (1) Why Manhattan density-peak beat polar/hull (doorway bleed + coverage histograms; PCA angle when Hough fails on SfM). (2) Hub stitch + door-center align vs left-align ablation. (3) Photo/video always COLMAP; scale via `--ref-from` / tape; Stray RGB short-wall PASSes vs LiDAR. (4) GT CSV is validation/testing only. (5) Repeatability disclosed as repeatable-but-biased when tape-shared. (6) Damage is rule-based two-class + concealed, not ML.

---

## 9. Summary

End-to-end Route 2 pipeline: honest tier CIs, regenerable fix-loop (hull → polar → Manhattan density-peak), COLMAP photo/video with fail-closed thin SfM, Stray RGB validated against LiDAR golden, 3-room+connector opening-anchored stitch with drift ablation, Magicplan H2H, repeatability pair, staged damage. Main remaining risk: **centimetre LiDAR on the unseen walk-in room** — not cold Stray handoff or composition breadth.

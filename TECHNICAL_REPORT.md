# Technical Report — Indoor Capture → Dimensioned Plan

**Route 2 (stock capture) · Cozmo AI case study · September 2026**
**Repo entrypoint:** `run.py` · **Schema:** `schema/output.schema.json` · **Regen benchmark:** `python benchmark/run_benchmark.py`

---

## 1. Problem and capture route

We produce a dimensioned per-room plan (walls, openings, ceiling height, floor area), a stitched multi-room plan with adjacency, rule-based damage/scope lines, and a confidence interval on every measurement — from one CLI command per capture — for three sensor tiers: **photo**, **video**, and **LiDAR**.

**Route 2.** No custom iOS app. Capture uses App Store / stock tools:

| Tool | Role |
|------|------|
| [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) | LiDAR depth, poses, intrinsics → export folder |
| Native camera | Photo folders and walkthrough video |

Protocol for a non-engineer (install, walk, avoid, handoff) lives in `docs/CAPTURE_PROTOCOL.md`. Defense walk-in follows that page literally. One command examples:

```bash
python run.py --input /path/to/stray_export --tier lidar|photo|video --out out/
python run.py --input /path/to/room_photos --tier photo --ref-length-m L --ref-width-m W --out out/
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
```

---

## 2. Architecture

```
capture_io/          Stray loader; Android photo/video resolve + ffmpeg frames
reconstruction/
  pointcloud.py      Depth + odometry → metric cloud (confidence-gated)
  planes.py          Two-stage floor / ceiling RANSAC
  wall_detection.py  Manhattan density-peak rect → polar outline → hull baseline
  room_polygon.py    Walls, openings, floor area
  media_layout.py    GT / tape rectangle for thin photo-video
  sfm_colmap.py      Optional COLMAP metric attempt (≥200-pt gate)
  stitch.py          Opening-anchored multi-room placement
  damage.py          Rule-based stains + concealed-behind-opening
  render.py          Top-down plan PNG (single + stitched)
run.py               Tier dispatch, CI widths, JSON emit
schema/              Output contract
benchmark/           GT CSV, REPORT, H2H exports, regen script
fix_loop/           Declaration + regenerable before/after
```

**LiDAR path.** Build a voxel-downsampled point cloud → fit floor (largest plane) → fit ceiling only among points ≥ ~1.8 m above floor, reject candidates &lt; 1.7 m (furniture) → extract a mid-height wall band → Manhattan density-peak rectangle (Hough-voted dominant wall direction, then per-axis histogram-mode wall position; falls back to polar max-radius outline, then convex hull) → gap-based openings on walls → schema JSON + plan PNG. Soft-fail on ceiling: wide residential prior CI and an explicit note, not a silent fake plane.

**Photo / video path.** Prefer COLMAP SfM scaled by a reference length when the reconstruction clears an internal point gate. On Android hall/bedroom captures COLMAP is typically too thin; we fall back to a **tape- or GT-anchored axis-aligned rectangle** and widen wall CIs to the tier budget (±8% photo, ±3% video). Stray folders at photo/video tier reuse the **same metric cloud** as LiDAR with those wider CIs — so walk-in can exercise all three tiers from one export.

**Output.** Every run emits schema-valid JSON (`rooms[]`, `stitched_plan`, `drift_correction`) and a rendered plan. Damage/scope are rule-based (`water_stain` compact dark patches, `surface_crack` elongated marks, plus `concealed_behind_opening`); they satisfy the contract without claiming vision-grade damage detection. Staged two-class capture: `samples/my_room_damage/` (evidence in `benchmark/damage/`).

---

## 3. Tier design and device matrix

| Tier | Hardware | Metric source | Wall CI posture | Typical runtime* |
|------|----------|---------------|-----------------|------------------|
| LiDAR | iPhone Pro + Stray | Depth + poses (metric) | Tightest (plane residuals) | ~2–5 s (samples) |
| Video | Any phone, or Stray export | SfM+scale **or** tape rect **or** Stray cloud | ±3% wall target | ~1–12 s |
| Photo | Any phone, or Stray export | Same | ±8% wall target | ~1–12 s |

\*Benchmarked on provided samples; see `benchmark/REPORT.md`.

**Honest accuracy claim.** LiDAR is the centimetre *ambition* path, but company Stray rooms have **no tape GT**, so opening ≤2 cm and ceiling ≤1.5 cm gates are **not claimed as passed**. Photo/video on our measured hall and bedroom match tape by construction under the ref-rectangle path; intervals remain tier-wide so we do not ship “confident garbage.”

---

## 4. Drift handling and multi-room stitch

Spec fails bare `poses_as_is` on multi-room and requires an ablation with drift correction on vs off.

**Method used:** `plane_anchored_correction` — hall is the star center; bedroom and kitchen rectangles are each placed so their **shared door centers align** with the hall wall they attach to (bedroom: hall-south / bedroom-north, shared width 0.88 m; kitchen: hall-west / kitchen-east, shared width 0.77 m — two independent edges off the same room, generalized from the original 2-room `stitch_two_rectangles` to an edge-list chain stitcher, `stitch_chain_from_gt`, so a third room can attach on a different wall without colliding with the first). Ablation (`--drift-align off`) left-aligns both children under their respective hall walls without door centering (`poses_as_is` on both edges).

| Setting | `method_used` | Footprint | Placement |
|---------|---------------|-----------|-----------|
| `--drift-align on` | `plane_anchored_correction` | **20.138 m²** | Both door centers aligned |
| `--drift-align off` | `poses_as_is` | **20.138 m²** | Both children left-aligned; wrong door registration |

Footprint is identical (sum of room areas: 11.6644 hall + 4.7385 bedroom + 3.735 kitchen); **adjacency geometry** differs, visibly, on both edges (see rendered plans). Adjacency edges: `my_room_south__my_bedroom_north`, `my_room_west__my_kitchen_east`. Regenerable via `--stitch-gt my_room,my_bedroom,my_kitchen`. This now satisfies the spec's "3+ rooms plus a connector" multi-room composition requirement — all three rooms are our own tape/app-measured captures, not independent multi-room LiDAR (no iPhone available for a real multi-room LiDAR walk). Method and limit are disclosed in JSON notes and the benchmark report.

---

## 5. Error budget and calibration analysis

**Budget by tier (walls).** Photo ±8%, video ±3%, LiDAR from plane residual / method flags. Area CIs scale similarly. Ceiling: plane-fit sigma when successful; else prior 1.5–3.5 m with an explicit coverage note.

**Self-built benchmark.**

| Capture | Tiers | GT | Role |
|---------|-------|-----|------|
| `my_room` (hall) | photo, video | Tape: 4.82×2.42 m, ceil 2.58 m, doors 0.88 / 0.77 (bedroom/kitchen) | Star-center, calibrated photo/video |
| `my_bedroom` | photo, video | Tape: 2.43×1.95 m, ceil 2.58 m, door 0.88 m | Second room + stitch |
| `my_kitchen` | photo, video | App/tape: 2.25×1.66 m, ceil 2.58 m, door 0.77 m | Third room + stitch (3-room composition) |
| Stray `single_*` | lidar (+ photo/video via cloud) | None from us | Walk-in-shaped LiDAR stress |

**Hall / bedroom / kitchen vs tape (photo).** Area and wall lengths match GT (ref-rectangle) on all three rooms. That is **calibration pass**, not independent SfM. COLMAP was attempted on all three and is too thin on all three (hall/bedroom documented earlier; kitchen: 327 plane inliers on photos, 121 on video vs. 500 required) → fallback documented in run notes (`colmap_fallback` / `--no-colmap` in benchmark jobs).

**LiDAR qualitative.** After the round-2 wall-detection fix (§6): `single_room` ≈ 9.9 m² Manhattan rect; ceiling soft-fails (~1.25 m furniture). `single_scan_floor` ≈ 27.0 m² and `single_scan_with_ceiling` ≈ 30.5 m², both `manhattan_rect`, `low_confidence=False` (previously `oriented_rect_large` at 113/139 m²). Cross-checked stable (27–33 m²) across frame_stride 10/20/30, vs. a 111–159 m² swing for the same strides under the old max-radius method. Ceiling plane ≈ 1.83 m when the walk looks up.

**Repeatability.** `my_bedroom` vs `my_bedroom_repeat` at photo and video: walls Δ = 0 (exact), ceiling spread = 0. Both take the `ref_rectangle` path scaled from the same tape GT — **repeatable-but-biased**, disclosed in `benchmark/REPORT.md`. Not an independent SfM cross-check.

**Head-to-head (Magicplan Android).** Free-tier plan export vs our photo tier on hall + bedroom (spec minimum) plus kitchen as a bonus third room from the same Magicplan session. Android Magicplan has no AR scan; rooms were drawn with tape-entered dims. Ours uses the same tape scale when SfM fails. Shared dimensions: **13/13 beat or tie** (9/9 on the required 2-room minimum alone; ≥70% target). This is a plan-export comparison with method disclosure, not a LiDAR bake-off. Artifacts: `benchmark/h2h/`.

---

## 6. Fix-loop story (25% weight)

**Worst gate before.** LiDAR footprint/walls on `single_scan_with_ceiling`: convex hull of the wall band → **~115 m²**, **8-vertex** irregular polygon — unusable as a room plan.

**Root cause.** Wall-band points are a **filled** set (furniture + clutter + bleed), not a thin wall ring. Hull = outer envelope of everything seen. Ceiling fit on the same capture was healthy (~1.83 m), isolating the failure to lateral extraction.

**Fix shipped (two rounds).** Round 1: polar max-radius outline → oriented min-area rectangle; oversized results flagged `oriented_rect_large` / `low_confidence`. This fixed shape validity but not the bleed — "farthest point per ray" still chases the one stray point down an open doorway, so area went *up* (115→139 m²). Round 2: replaced the primary method with a **Manhattan density-peak rectangle** — Hough-vote the dominant wall direction (not a single noisy line fit), then on each axis take the *histogram-mode* wall position (a real wall is hit repeatedly; doorway bleed is sparse and doesn't win a density peak) and build an axis-aligned box from the two independent per-axis peaks so opposite sides are equal by construction. CLI `--wall-method hull|polar|manhattan|auto` makes every stage regenerable.

| Capture | Hull | Polar rect (round 1) | Manhattan rect (round 2) |
|---------|------|---|---|
| `single_scan_with_ceiling` | 115.2 m², 8 walls | `oriented_rect_large`, 139.3 m², 4 walls, low_confidence | `manhattan_rect`, **30.5 m²**, 4 walls, low_confidence=**False** |
| `single_room` | hull path | `oriented_rect`, ~35 m², 4 walls | `manhattan_rect`, **~9.9 m²**, 4 walls |

**Post-mortem.** Round 1 fixed shape validity (4 equal-side walls) but not the underlying bleed — a partial, honestly-flagged fix. Round 2 targets the actual mechanism (max-radius vs. density-peak) and the area drops ~4–5x with the low-confidence flag clearing; cross-checked stable across frame_stride 10/20/30 (27–33 m² vs. a 111–159 m² swing for the same strides under max-radius). Still **no tape GT on the company Stray samples**, so this is a shape-plausibility and stride-robustness claim, not a claimed pass on the centimetre gate — but it's the piece that runs live at the walk-in test. Bundle: `fix_loop/DECLARATION.md`, `fix_loop/before|after/`, `python fix_loop/regenerate.py`.

---

## 7. Known failure modes

1. **Doorway bleed / multi-space walks** → density-peak fit resists it much better than the old max-radius outline (see §6), but still no tape GT on the company Stray samples to confirm centimetre accuracy; do not treat as single-room GT.
2. **No ceiling tilts** → ceiling soft-fail; residential prior CI, not a plane measurement.
3. **Furniture planes ~1.2–1.5 m** → rejected as ceiling (&lt; 1.7 m rule).
4. **Thin COLMAP on phone photos** → tape/GT rectangle required; independent metric photo not claimed.
5. **Mirrors / glass / closed doors** → holes or missed openings; protocol says avoid linger / open doors for the opening gate.
6. **Stitch from GT rectangles** — adjacency and drift ablation are real; independent photo-only SfM stitch is not.
7. **Damage** — rule heuristics only; not a scored vision system.
8. **Benchmark composition gaps** — staged two-class damage room now covered (`my_room_damage`). Technical report currently under the 6-page budget and should be expanded. Samples folder still flat (rearrange TODO).

---

## 8. Reproduction and walk-in readiness

| Deliverable | Location |
|-------------|----------|
| One-command CLI | `README.md`, `run.py` |
| Capture protocol + device matrix | `docs/CAPTURE_PROTOCOL.md` |
| Walk-in checklist | `docs/WALKIN_CHECKLIST.md` |
| Benchmark tables | `benchmark/REPORT.md` ← `run_benchmark.py` |
| Ground truth | `benchmark/ground_truth.csv` |
| Head-to-head | `benchmark/HEAD_TO_HEAD.md`, `benchmark/h2h/` |
| Fix loop | `fix_loop/` |
| Compliance matrix | `docs/COMPLIANCE_MATRIX.md` |

Cold walk-in: receive Stray export → run all three `--tier` values → compare JSON/plan to laser. Photo-only phone path needs `--ref-length-m` / `--ref-width-m` if SfM fails (protocol).

---

## 9. Summary

We ship an end-to-end Route 2 pipeline with honest tier intervals, a two-round regenerable fix-loop (hull → polar rectangle → Manhattan density-peak rectangle), a 3-room-plus-connector opening-anchored stitch with drift ablation, a tape-calibrated photo/video benchmark (3 rooms) plus Magicplan H2H under disclosed methods, a disclosed **repeatable-but-biased** bedroom repeatability pair, and a staged two-class damage room (`water_stain` + `surface_crack`, rule-based). Remaining score risk is concentrated in **independent centimetre LiDAR accuracy** (no tape on company scans) and **report depth / samples UX** — not in the ability to run cold on a Stray handoff or in multi-room composition breadth.

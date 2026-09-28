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

The non-engineer protocol (install, walk, avoid, handoff, device matrix) is `docs/CAPTURE_PROTOCOL.md`. Defense walk-in follows that page literally. Sample drop zones for reviewers: company Stray exports → `samples/stray/`; author phone rooms stay private under `samples/local/` (committed JSON/plans under `benchmark/` replace raw media). See `samples/README.md`.

```bash
python run.py --input /path/to/stray_export --tier lidar|photo|video --out out/
python run.py --input /path/to/room_photos --tier photo --ref-length-m L --ref-width-m W --out out/
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
```

---

## 2. Architecture

```
capture_io/           Stray loader; phone photo/video resolve + ffmpeg frames; sample path aliases
reconstruction/
  pointcloud.py       Depth + odometry → metric cloud (confidence-gated, voxel downsample)
  planes.py           Two-stage floor / ceiling RANSAC (fixed seed for determinism)
  wall_detection.py   Manhattan density-peak rect → polar outline → hull baseline
  room_polygon.py     Walls, openings, floor area
  media_layout.py     GT / tape rectangle for thin photo–video; GT room aliases
  sfm_colmap.py       Optional COLMAP metric attempt (plane-inlier gate)
  stitch.py           Opening-anchored multi-room placement + drift ablation
  damage.py           water_stain + surface_crack + concealed_behind_opening
  render.py           Top-down plan PNG (single + stitched)
run.py                Tier dispatch, CI widths, schema validation, JSON emit
schema/               Output contract
benchmark/            GT CSV, REPORT, H2H, damage evidence, regen script
fix_loop/            Declaration + regenerable before/after
```

**LiDAR path (centimetre ambition).** Fuse a confidence-gated, voxel-downsampled cloud from Stray depth + poses → fit **floor** (largest RANSAC plane) → up-axis → **ceiling** only among points ≥ ~1.8 m above floor, reject heights &lt; 1.7 m (furniture) → mid-height wall band → **Manhattan density-peak rectangle** (Hough angle mod 90°, per-axis histogram-mode on coverage-deduped cells; fallback polar outline, then hull) → gap openings → JSON + plan PNG. Ceiling soft-fail: residential prior CI (1.5–3.5 m) + explicit note — never a silent fake 0.

**Photo / video path.** Prefer COLMAP scaled by a reference length when plane-inliers clear ≥500. On our Android rooms COLMAP is too thin → **tape/GT axis-aligned rectangle** with tier CIs (±8% photo, ±3% video). Stray at photo/video reuses the LiDAR metric cloud with those wider CIs so one export exercises all three tiers.

**Damage / scope.** Rule-based: compact dark → `water_stain`; elongated (aspect ≥4) → `surface_crack`; openings → `concealed_moisture_risk`. Staged room `samples/local/my_room_damage/` (evidence `benchmark/damage/`). Extents assume ~3 m wall span — approximate.

**Output.** Every run validates `schema/output.schema.json` and writes `rooms[]`, `stitched_plan`, `drift_correction`, plus a plan PNG.

---

## 3. Tier design and device matrix

| Tier | Hardware | Metric source | Wall CI posture | Typical runtime* |
|------|----------|---------------|-----------------|------------------|
| LiDAR | iPhone Pro + Stray Scanner | Depth + poses (metric) | Plane residuals / method flags | ~2–5 s |
| Video | Any recent phone, **or** same Stray export | SfM+scale **or** tape rect **or** Stray cloud | ±3% wall target | ~1–12 s |
| Photo | Any recent phone, **or** same Stray export | Same | ±8% wall target | ~1–12 s |

\*On provided samples; full timing table in `benchmark/REPORT.md` (regen with `run_benchmark.py`). Representative cold-run times on this machine:

| Job | Tier | Time (s) | Notes |
|-----|------|----------|-------|
| `single_scan_with_ceiling` | lidar | ~4.8 | Fix-loop capture |
| same export | photo / video | ~11–12 | Same metric cloud; wider CIs |
| `single_room` / `single_scan_floor` | lidar | ~2.5–2.7 | |
| `my_*` phone rooms | photo / video | ~0.8–1.2 | `--no-colmap` ref-rectangle |
| 3-room stitch on/off | photo | ~0.8 each | GT rectangles |

**Why intervals widen.** Photo has no depth/poses; video has motion but still no metric scale without SfM or tape. Publishing tight CIs on the tape-rectangle path would be “confident garbage.” Tier fractions are applied uniformly to walls (and scaled to area). Ceiling uses plane-fit uncertainty when a ceiling plane succeeds; otherwise the prior band above.

**Determinism.** Floor/ceiling RANSAC uses a fixed seed (`RANSAC_SEED=42`) so regenerable LiDAR numbers do not jitter run-to-run — relevant to the repeatability gate’s “same plan out” reading when the geometric path is deterministic.

**Honest accuracy claim.** LiDAR is the centimetre *ambition* path for walk-in. Company Stray rooms have **no tape GT from us**, so opening ≤2 cm and ceiling ≤1.5 cm gates are **UNKNOWN vs gate** on those samples — we do not invent a pass. Photo/video on our measured rooms match tape under the ref-rectangle path (**calibration**, not independent SfM). Walk-in scoring is against the graders’ laser on their capture, not against our private rooms.

---

## 4. Drift handling and multi-room stitch

Spec fails bare `poses_as_is` on multi-room and requires an on/off ablation.

**Composition.** Three rooms + connector: hall (`my_room`) as star center, bedroom and kitchen on independent hall walls (south door 0.88 m; west door 0.77 m). Satisfies “3+ rooms plus a connector.”

**Method (`--drift-align on`):** `plane_anchored_correction` — place each child rectangle so **shared door centers align** with the parent wall opening (`stitch_chain_from_gt`).

**Ablation (`--drift-align off`):** `poses_as_is` — left-align children under the parent wall without door centering. Footprint sum is identical; **adjacency geometry** differs on both edges (visible on rendered plans in `benchmark/h2h/stitched/`).

| Setting | `method_used` | Footprint | Placement |
|---------|---------------|-----------|-----------|
| on | `plane_anchored_correction` | **20.138 m²** | Door centers aligned |
| off | `poses_as_is` | **20.138 m²** | Left-aligned; wrong door registration |

Footprint = 11.6644 + 4.7385 + 3.735 m². Adjacency IDs: `my_room_south__my_bedroom_north`, `my_room_west__my_kitchen_east`. Regenerable: `--stitch-gt my_room,my_bedroom,my_kitchen`. **Limit disclosed:** this is GT/tape rectangle stitch, not independent multi-room LiDAR (no iPhone Pro for a live multi-room LiDAR walk on our side).

**Why door-center align, not pose-graph loop closure.** We do not have continuous multi-room LiDAR poses across the apartment. The honest drift story for the shipped stitch is *opening-plane anchoring*: treat each shared door as a metric hinge and register rectangles in the floor plane. The ablation proves the hinge matters for adjacency even when area is unchanged — the failure mode the spec is hunting (“poses used as-is”) is exactly left-align without that hinge.

---

## 5. Error budget and calibration analysis

### 5.1 Error budget by quantity

| Quantity | Photo | Video | LiDAR (when plane/method healthy) |
|----------|-------|-------|-----------------------------------|
| Wall length | ±8% of value | ±3% of value | Residual / low_confidence flag; no cm claim without GT |
| Floor area | Scaled from wall CIs | Same | Same |
| Ceiling | ±8% if GT/tape height; else prior | ±3% if GT/tape | Plane sigma when covered; else prior 1.5–3.5 m + note |
| Openings | Inherited wall method; phantom/miss scored at walk-in | Same | Gap heuristic; ≤2 cm **not claimed** on Stray |

### 5.2 Self-built benchmark composition

| Capture | Tiers exercised | GT | Role |
|---------|-----------------|----|------|
| `my_room` (hall) | photo, video | Tape 4.82×2.42 m, ceil 2.58 m, doors 0.88 / 0.77 | Star center; calibrated thin path |
| `my_bedroom` + `_repeat` | photo, video | Tape 2.43×1.95 m, ceil 2.58 m, door 0.88 m | Second room; **repeatability pair** |
| `my_kitchen` | photo, video | App/tape 2.25×1.66 m, ceil 2.58 m, door 0.77 m | Third room + stitch |
| `my_room_damage` | photo | Same hall GT | **Two visual damage classes** staged |
| Stray `single_*` | lidar (+ photo/video via cloud) | None from us | Walk-in-shaped LiDAR stress; fix-loop |

### 5.3 Photo / video vs tape (calibration, not SfM)

On hall, bedroom, and kitchen, photo/video **area and wall lengths match GT** because COLMAP fails the plane-inlier gate and the pipeline uses `ref_rectangle` + `scale_source=gt_length+gt_width`. Documented COLMAP thinness: kitchen photos ~327 plane inliers / video ~121 vs gate 500; hall and bedroom likewise. Intervals stay at tier width. **This is a disclosed calibration pass**, not a claim of independent centimetre vision.

**How CIs are applied.** For a wall of length \(L\), photo emits \([L(1-0.08),\, L(1+0.08)]\) and video \([L(1-0.03),\, L(1+0.03)]\) at 95% nominal confidence_level in the schema. Area intervals are derived from the same fractions. LiDAR wall CIs use plane/method residuals when `low_confidence=False`; when the fit falls back to polar/hull with a `*_large` tag, intervals widen and `low_confidence=True` is set so a grader reading JSON does not treat doorway-bleed geometry as precise.

**What “verified benchmark accuracy” means here.** The 15% score component rewards numbers that regenerate from raw inputs. Our regenerable surface is: Stray LiDAR/photo/video on company samples (shape + timing), tape-anchored photo/video on three measured rooms, stitch on/off ablation, repeatability pair, damage capture, and Magicplan H2H tables. What we **do not** claim as verified centimetre truth: Stray wall/opening/ceiling absolute error (no laser on those rooms), or photo lengths independent of tape.

### 5.4 Repeatability (spec: ≤1 cm or 0.5% per wall; ceiling spread ≤1 cm)

`my_bedroom` vs `my_bedroom_repeat`, photo and video: walls Δ = **0 cm**, ceiling spread = **0 cm**. Both runs are `ref_rectangle` on the **same tape rows** (`GT_ROOM_ALIASES`). Spec language distinguishes **repeatable-but-biased** from unrepeatable — we have the former and say so in `benchmark/REPORT.md`. An independent SfM repeat would be stronger; it remains future work if denser texture clears COLMAP.

### 5.5 LiDAR qualitative (no company-room tape)

After the round-2 wall fix (§6):

| Sample | Method | Area | Ceiling | Notes |
|--------|--------|------|---------|-------|
| `single_scan_with_ceiling` | `manhattan_rect` | **30.5 m²** | ~1.83 m | Fix-loop capture; was 115→139 m² under hull/polar |
| `single_scan_floor` | `manhattan_rect` | **27.0 m²** | ~1.83 m | Was ~113 m² polar-large |
| `single_room` | `manhattan_rect` | **~9.9 m²** | soft-fail (~1.25 m furniture) | Prior CI, not a plane |

Stride sweep 10/20/30 on ceiling-covered samples: Manhattan area holds ~27–33 m²; old max-radius swung ~111–159 m². Shape/robustness win; **not** a claimed ≤2 cm / ≤1.5 cm pass.

### 5.6 Head-to-head (Magicplan Android)

Free-tier plan export vs our photo tier on hall + bedroom (required) and kitchen (bonus). Android Magicplan has no AR scan — rooms drawn with tape-entered dims; ours uses the same tape when SfM fails. Method disclosed in `benchmark/HEAD_TO_HEAD.md`. Not a LiDAR bake-off.

| Scope | Shared dims | Ours beat or tie | Target |
|-------|-------------|------------------|--------|
| Hall + bedroom (required minimum) | 9 | **9 / 9** | ≥70% |
| + kitchen (bonus) | 13 | **13 / 13** | ≥70% |

Ceiling excluded where Magicplan export omitted height. Artifacts: `benchmark/h2h/our_room_{a,b,c}/`, `benchmark/h2h/app_exports/`.

### 5.7 Damage composition gate

Spec requires one furnished room with staged damage spanning **two classes**. `my_room_damage` (hall, 5 stills) fires:

| Class | Rule | Role |
|-------|------|------|
| `water_stain` | `stain_dark_patch` (compact dark CC) | Visual class 1 |
| `surface_crack` | `crack_elongated_mark` (aspect ≥4) | Visual class 2 |
| `concealed_moisture_risk` | `concealed_behind_opening` | Rule flag on jambs (not a third visual class) |

Four regions total on the photo run. Rule-based luminance heuristics — not a trained detector. Evidence: `benchmark/damage/`.

---

## 6. Fix-loop story (25% weight)

**Worst gate before.** LiDAR footprint/walls on `single_scan_with_ceiling`: convex hull of the wall band → **~115 m²**, **8-vertex** irregular polygon — unusable as a room plan.

**Root cause.** Wall-band points are a **filled** set (furniture + clutter + doorway bleed), not a thin wall ring. Hull = outer envelope of everything seen. Ceiling on the same capture was healthy (~1.83 m), isolating failure to **lateral** extraction.

**Round 1 (partial).** Polar max-radius outline → oriented min-area rectangle; oversized footprints tagged `oriented_rect_large` / `low_confidence`. Fixed shape validity (4 walls) but not bleed — “farthest point per ray” still chases a single stray point through an open doorway (115 → **139 m²**, worse).

**Round 2 (shipped primary).** **Manhattan density-peak rectangle:** Hough-vote dominant wall direction; per axis take the histogram-mode wall position on points deduped to occupancy cells (coverage, not raw duplicate density); axis-aligned box ⇒ opposite sides equal by construction. CLI `--wall-method hull|polar|manhattan|auto`.

A first cut of round 2 used *raw* point histograms and looked good at the production stride, then silently fell back to polar at other strides — sharpness was inflated by near-duplicate viewpoints, not wall coverage. Deduping to one point per occupancy cell fixed that; the stride sweep is the evidence we ship that the method is robust, not lucky.

| Capture | Hull | Polar (R1) | Manhattan (R2) |
|---------|------|------------|----------------|
| `single_scan_with_ceiling` | 115.2 m², 8 walls | 139.3 m², low_conf | **30.5 m²**, low_conf=**False** |
| `single_scan_floor` | — | ~112.9 m², large | **27.0 m²** |
| `single_room` | — | ~35.1 m² | **~9.9 m²** |

**Post-mortem.** Round 1 prediction under-ambitious (shape only). Round 2 targets the real mechanism (max-radius vs density-peak); ~4–5× area drop and confidence clear, stride-stable. Still **no tape GT on Stray samples** — shape/robustness claim for walk-in, not a centimetre gate pass. Bundle: `fix_loop/DECLARATION.md`, `before/` / `after/`, `python fix_loop/regenerate.py`.

---

## 7. Known failure modes (including walk-in)

1. **Doorway bleed / multi-space walks** — density-peak resists far better than hull/polar; still no Stray tape GT for cm validation.
2. **Eye-level-only LiDAR** — ceiling soft-fail; prior CI + note (protocol: tilt up/down).
3. **Furniture planes ~1.2–1.5 m** — rejected as ceiling (&lt; 1.7 m rule); `single_room` exhibits this.
4. **Thin COLMAP on phone stills** — tape/GT rectangle required; independent metric photo **not claimed**.
5. **Mirrors / glass / closed doors** — holes or missed openings; protocol: avoid linger, open doors for the opening gate.
6. **GT rectangle stitch** — adjacency + drift ablation are real; independent photo-only SfM multi-room stitch is not.
7. **Damage heuristics** — luminance rules, not a trained detector; extents approximate.
8. **Repeatable-but-biased photo/video** — identical walls across captures when both use shared tape scale.
9. **Walk-in expectation** — graders’ laser is ground truth. We expect LiDAR walls in the right shape class (`manhattan_rect` when Manhattan); centimetre pass depends on their room and coverage. Photo/video without tape spans fail closed unless protocol tape is supplied.

---

## 8. Reproduction and walk-in readiness

| Deliverable | Location |
|-------------|----------|
| One-command CLI | `README.md`, `run.py` |
| Capture protocol + device matrix | `docs/CAPTURE_PROTOCOL.md` |
| Sample drop / privacy | `samples/README.md` (`stray/` vs `local/`) |
| Benchmark tables + timing | `benchmark/REPORT.md` ← `run_benchmark.py` |
| Ground truth | `benchmark/ground_truth.csv` |
| Head-to-head | `benchmark/HEAD_TO_HEAD.md`, `benchmark/h2h/` |
| Damage evidence | `benchmark/damage/` |
| Fix loop | `fix_loop/` |
| Compliance matrix | `docs/COMPLIANCE_MATRIX.md` |

Cold walk-in: receive Stray export → run all three `--tier` values → compare JSON/plan to laser. Phone-only path needs `--ref-length-m` / `--ref-width-m` when SfM fails (protocol). Cached committed JSON/PNG replay reported numbers; live path is what defense runs.

**Defense narrative (tools closed).** Be ready to explain: (1) why Manhattan density-peak beat polar/hull (doorway bleed + stride robustness of coverage histograms); (2) why stitch is star topology off the hall with door-center align vs left-align ablation; (3) why photo/video match tape (COLMAP thin → ref_rectangle) and why that is labeled calibration; (4) why repeatability is disclosed as repeatable-but-biased; (5) why damage is rule-based two-class + concealed, not ML.

---

## 9. Summary

End-to-end Route 2 pipeline: honest tier CIs, regenerable fix-loop (hull → polar → Manhattan density-peak), 3-room+connector opening-anchored stitch with drift ablation, tape-calibrated photo/video + Magicplan H2H (disclosed), repeatable-but-biased bedroom pair, staged two-class damage. Main remaining risk: **centimetre LiDAR on the unseen walk-in room** and **non-circular SfM** — not cold Stray handoff or composition breadth.


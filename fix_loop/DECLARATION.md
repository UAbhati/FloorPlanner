# Fix-loop declaration

## 1. Worst-performing gate (before)

**Gate:** Floor footprint / wall lengths on LiDAR single-room captures (feeds walk-in + opening gates).

**Failing number (regenerable):** on `samples/stray/single_scan_with_ceiling`, convex-hull wall extraction produced **floor area ≈ 115.15 m²** with an 8-vertex non-rectangular polygon (`wall_method=convex_hull`). That is not a usable single-room plan (openings and wall CIs ride on the same wrong boundary).

Reproduce before:
```bash
source .venv/bin/activate
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar \
  --wall-method hull --out fix_loop/before/
```

## 2. Root-cause hypothesis + evidence

**Hypothesis:** The wall-band point cloud is a **filled** volume (furniture + clutter + doorway bleed), not a thin wall ring. Convex hull of that set is the outer envelope of everything LiDAR saw, not the room walls.

**Evidence:**
- `NOTES.md` (2026-09-27): hull over wall-band → 115 m²; scatter plot fills the interior.
- Manhattan 2D line-RANSAC experiment failed to assemble a valid rectangle (`reconstruction/wall_detection.py` history / `memory.md`).
- Same capture’s ceiling plane fit is healthy (~1.83 m), so the failure is specifically **lateral wall extraction**, not global tracking collapse.

## 3. Fix shipped + predicted number

**Fix (two rounds).**

Round 1 (first pass): polar max-radius outline → oriented min-area rectangle (`fit_room_walls`), with oversized footprints tagged `oriented_rect_large` / low_confidence instead of silently trusting a hull. This turned the 8-vertex hull junk into an honest 4-wall rectangle, but "farthest point per ray" still chases the single farthest doorway-bleed point on any ray that looks through an opening — footprint stayed inflated (115 m² → 139 m², *larger*, not smaller).

Round 2 (this fix): replaced the primary method with a **Manhattan density-peak rectangle**. Rasterize the wall-band cloud, Hough-vote for the dominant wall direction (mod 90°) instead of fitting a line to a noisy subset, rotate into that frame, and on each of the 2 axes find the *histogram-mode* wall position in the outer part of each half — a physical wall is hit repeatedly across the whole walk (sharp peak); sparse bleed points past an open doorway are not (flat). Build an axis-aligned box from the 4 independent peak positions and rotate back — opposite sides are equal by construction. Falls back to the round-1 polar rect, then hull, if no dominant angle or peak is confident. CLI: `--wall-method auto|manhattan|polar|hull`.

**Predicted after (round 2):** a materially smaller, still-4-wall footprint on both ceiling scans — no longer chasing bleed through the doorway — checked for stride-robustness (not just a single lucky sample).

**Observed after (regenerated):**
| Capture | Hull (baseline) | Polar rect (round 1) | Manhattan rect (round 2) |
|---------|---|---|---|
| `single_scan_with_ceiling` | 115.2 m², 8-vertex hull | `oriented_rect_large`, **139.3 m²**, low_confidence=True | `manhattan_rect`, **30.5 m²**, low_confidence=**False** |
| `single_scan_floor` | — | `oriented_rect_large`, **112.9 m²** | `manhattan_rect`, **27.0 m²** |
| `single_room` | — | `oriented_rect`, **35.1 m²** | `manhattan_rect`, **9.9 m²** |

Cross-checked at frame_stride 10/20/30 on both ceiling-covered samples: Manhattan area holds in a 27–33 m² band (not the wild 111–159 m² swing polar/hull showed across the same strides) — the density-peak signal, unlike max-radius, doesn't depend on how many points happen to land on stray doorway-bleed rays.

**Post-mortem.** Round 1's prediction ("4 walls, maybe still flagged large") was directionally right but under-ambitious — it fixed shape validity, not the bleed itself. Round 2 fixes the actual root cause (max-radius vs density-peak) and the area movement is real: **~4–5x smaller footprint, `low_confidence` cleared**, gate moves from "shape valid but flagged inflated" toward "plausible single-room rectangle." Still **no tape GT on the company Stray samples**, so this is not a claimed pass on the ≤2 cm opening / wall-accuracy gate — it's a shape-plausibility and stride-robustness win that directly matters for the walk-in test, where LiDAR wall detection runs cold on an unseen room.

Reproduce after:
```bash
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar \
  --wall-method auto --out fix_loop/after/
python run.py --input samples/stray/single_room --tier lidar \
  --wall-method auto --out fix_loop/after/
```

Or one shot:
```bash
python fix_loop/regenerate.py
```

## 4. Diff pointer

Readable code diff: `reconstruction/wall_detection.py` (Manhattan density-peak fit + polar outline fallback) + `reconstruction/room_polygon.py` (`build_room_polygon` method switch) + `run.py` (`--wall-method auto|manhattan|polar|hull`).

Git: compare commits around the wall-extraction fix (`85e305d` and follow-ups) vs the earlier hull-only CLI (`1eae41b`); Manhattan density-peak rewrite is the most recent wall_detection.py commit.

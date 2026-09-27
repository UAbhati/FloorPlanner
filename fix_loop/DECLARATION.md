# Fix-loop declaration

## 1. Worst-performing gate (before)

**Gate:** Floor footprint / wall lengths on LiDAR single-room captures (feeds walk-in + opening gates).

**Failing number (regenerable):** on `samples/single_scan_with_ceiling`, convex-hull wall extraction produced **floor area ≈ 115.15 m²** with an 8-vertex non-rectangular polygon (`wall_method=convex_hull`). That is not a usable single-room plan (openings and wall CIs ride on the same wrong boundary).

Reproduce before:
```bash
source .venv/bin/activate
python run.py --input samples/single_scan_with_ceiling --tier lidar \
  --wall-method hull --out fix_loop/before/
```

## 2. Root-cause hypothesis + evidence

**Hypothesis:** The wall-band point cloud is a **filled** volume (furniture + clutter + doorway bleed), not a thin wall ring. Convex hull of that set is the outer envelope of everything LiDAR saw, not the room walls.

**Evidence:**
- `NOTES.md` (2026-09-27): hull over wall-band → 115 m²; scatter plot fills the interior.
- Manhattan 2D line-RANSAC experiment failed to assemble a valid rectangle (`reconstruction/wall_detection.py` history / `memory.md`).
- Same capture’s ceiling plane fit is healthy (~1.83 m), so the failure is specifically **lateral wall extraction**, not global tracking collapse.

## 3. Fix shipped + predicted number

**Fix:** Polar max-radius outline → oriented min-area rectangle (`fit_room_walls`), with oversized footprints tagged `oriented_rect_large` / low_confidence instead of silently trusting a hull. CLI default `--wall-method auto`.

**Predicted after:** on `single_scan_with_ceiling`, a **4-wall rectangle** (possibly flagged large if the scan spans multi-space); no more irregular 8-vertex hull. On `single_room`, a stable 4-wall rectangle.

**Observed after (regenerated):**
| Capture | Before | After |
|---------|--------|-------|
| `single_scan_with_ceiling` | hull, **115.2 m²**, 8 walls | `oriented_rect_large`, **139.3 m²**, **4 walls**, `low_confidence=True` |
| `single_room` | (hull path) | `oriented_rect`, **~35 m²**, **4 walls** |

**Post-mortem:** On the multi-space ceiling sample, area did not shrink — polar outline still sees adjacent space through openings — but the product is now an honest 4-wall rectangle with an explicit large/low-confidence flag instead of a confident-looking irregular hull. That is the gate movement we claim: **shape + confidence calibration**, not a false centimetre win on a multi-room walk.

Reproduce after:
```bash
python run.py --input samples/single_scan_with_ceiling --tier lidar \
  --wall-method auto --out fix_loop/after/
python run.py --input samples/single_room --tier lidar \
  --wall-method auto --out fix_loop/after/
```

Or one shot:
```bash
python fix_loop/regenerate.py
```

## 4. Diff pointer

Readable code diff: `reconstruction/wall_detection.py` (polar outline) + `reconstruction/room_polygon.py` (`build_room_polygon` method switch) + `run.py` (`--wall-method`).

Git: compare commits around wall extraction fix (`85e305d` and follow-ups) vs earlier hull-only CLI (`1eae41b`).

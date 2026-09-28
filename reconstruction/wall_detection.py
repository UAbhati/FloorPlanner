"""Wall / room-polygon detection from a top-down wall-band point cloud.

History (fix-loop before/after under ``fix_loop/``):
- Convex hull of the full wall band over-includes interior clutter (~115 m² junk).
- Raw 2D line-RANSAC (no global orientation step first) produced invalid,
  non-rectangular quads.
- Polar max-radius outline + oriented min-area rect (the first fix-loop fix)
  turned that into an honest 4-wall rectangle, but "max radius per ray" still
  chases the single farthest doorway-bleed point on any ray that looks through
  an opening, so oversized footprints stayed oversized.

Current primary approach — Manhattan density-peak rectangle:
1. Rasterize the wall-band cloud to an occupancy grid; run a Hough transform
   to find the dominant wall direction (mod 90°) by vote, not by fitting a
   single line to a noisy subset — this is the orientation step the earlier
   line-RANSAC attempt skipped.
2. Rotate points into that Manhattan frame. For each of the 2 axes, split at
   the median and find the *density peak* (histogram mode, not max extent) in
   the outer part of each half. A physical wall is hit repeatedly across the
   whole walk, so it is a sharp histogram peak; sparse doorway-bleed points
   beyond it are not, so they no longer win.
3. Build an axis-aligned box from the 4 peak positions and rotate it back.
   Because the box comes from 2 independent per-axis peaks (not 4
   independently intersected lines), opposite sides are equal by
   construction — the failure mode of the earlier line-RANSAC attempt.
4. If any peak is too flat to trust (ambiguous wall position) or no dominant
   angle is found, fall back to the polar max-radius outline, then to the
   convex hull (caller-selectable via --wall-method).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

N_ANGLE_BINS = 72
MIN_OUTLINE_POINTS = 24
MIN_CONTOUR_AREA_M2 = 1.5
# Captures may include adjacent space through doorways; still emit a rectangle
# and flag oversized footprints in the caller rather than falling back to hull.
MAX_SINGLE_ROOM_AREA_M2 = 40.0
GRID_RESOLUTION_M = 0.05
SIMPLIFY_EPSILON_FRAC = 0.02
OUTLIER_RAY_PERCENTILE = 90.0

# Manhattan density-peak fit
MANHATTAN_ANGLE_BINS = 180  # 0.5 deg resolution over the folded [0, pi/2) range
MANHATTAN_HOUGH_VOTE_FRAC = 0.3  # Hough vote threshold as a fraction of grid's larger dimension
MANHATTAN_HOUGH_MIN_VOTES = 20
WALL_DENSITY_BIN_M = 0.04
WALL_SEARCH_HALF_FRAC = 0.4  # only search the outer 40% of each half for the wall peak
MIN_WALL_SUPPORT_POINTS = 30
WALL_PEAK_MIN_SHARPNESS = 1.5  # peak bin count must be >= this x the mean nonzero bin count


@dataclass
class WallFitResult:
    vertices_2d: np.ndarray  # (N, 2)
    method: str  # "oriented_rect" | "occupancy_contour"
    floor_area_m2: float
    shell_point_count: int


def _polar_outline(points_2d: np.ndarray, n_bins: int = N_ANGLE_BINS) -> np.ndarray:
    center = np.median(points_2d, axis=0)
    delta = points_2d - center
    angles = np.arctan2(delta[:, 1], delta[:, 0])  # [-pi, pi]
    radii = np.linalg.norm(delta, axis=1)

    bin_ids = np.floor((angles + np.pi) / (2 * np.pi) * n_bins).astype(int)
    bin_ids = np.clip(bin_ids, 0, n_bins - 1)

    outline = []
    ray_radii = []
    for b in range(n_bins):
        mask = bin_ids == b
        if not np.any(mask):
            continue
        idx = np.argmax(radii[mask])
        pts = points_2d[mask]
        outline.append(pts[idx])
        ray_radii.append(radii[mask][idx])

    if len(outline) < MIN_OUTLINE_POINTS:
        return np.asarray(outline) if outline else points_2d[:0].reshape(0, 2)

    outline_arr = np.asarray(outline)
    ray_radii_arr = np.asarray(ray_radii)
    keep = ray_radii_arr <= np.percentile(ray_radii_arr, OUTLIER_RAY_PERCENTILE)
    if keep.sum() < max(MIN_OUTLINE_POINTS, len(outline_arr) // 2):
        return outline_arr
    return outline_arr[keep]


def _occupancy_contour(shell_2d: np.ndarray) -> np.ndarray | None:
    mins = shell_2d.min(axis=0) - GRID_RESOLUTION_M
    maxs = shell_2d.max(axis=0) + GRID_RESOLUTION_M
    span = maxs - mins
    cols = max(int(np.ceil(span[0] / GRID_RESOLUTION_M)), 8)
    rows = max(int(np.ceil(span[1] / GRID_RESOLUTION_M)), 8)

    grid = np.zeros((rows, cols), dtype=np.uint8)
    ix = np.clip(((shell_2d[:, 0] - mins[0]) / GRID_RESOLUTION_M).astype(int), 0, cols - 1)
    iy = np.clip(((shell_2d[:, 1] - mins[1]) / GRID_RESOLUTION_M).astype(int), 0, rows - 1)
    grid[iy, ix] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grid = cv2.morphologyEx(grid, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(largest, closed=True)
    approx = cv2.approxPolyDP(largest, SIMPLIFY_EPSILON_FRAC * peri, closed=True)
    verts_px = approx.reshape(-1, 2).astype(np.float64)
    return np.stack(
        [
            mins[0] + verts_px[:, 0] * GRID_RESOLUTION_M,
            mins[1] + verts_px[:, 1] * GRID_RESOLUTION_M,
        ],
        axis=1,
    )


def _oriented_rectangle(points_2d: np.ndarray) -> np.ndarray:
    rect = cv2.minAreaRect(points_2d.astype(np.float32))
    return cv2.boxPoints(rect).astype(np.float64)


def _polygon_area(vertices: np.ndarray) -> float:
    x, y = vertices[:, 0], vertices[:, 1]
    return float(0.5 * np.abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _rasterize(points_2d: np.ndarray, res: float = GRID_RESOLUTION_M) -> tuple[np.ndarray, np.ndarray]:
    mins = points_2d.min(axis=0) - res
    maxs = points_2d.max(axis=0) + res
    span = maxs - mins
    cols = max(int(np.ceil(span[0] / res)), 8)
    rows = max(int(np.ceil(span[1] / res)), 8)

    grid = np.zeros((rows, cols), dtype=np.uint8)
    ix = np.clip(((points_2d[:, 0] - mins[0]) / res).astype(int), 0, cols - 1)
    iy = np.clip(((points_2d[:, 1] - mins[1]) / res).astype(int), 0, rows - 1)
    grid[iy, ix] = 255
    return grid, mins


def _occupied_cell_centers(points_2d: np.ndarray, res: float = GRID_RESOLUTION_M) -> np.ndarray:
    """Dedupe points to one representative per occupied grid cell.

    Makes downstream density-peak stats depend on scanned coverage (how much
    of the room's surface was hit) rather than on raw point count, which
    otherwise swings with frame_stride / capture length and made the fit
    density-sensitive.
    """
    mins = points_2d.min(axis=0) - res
    ix = ((points_2d[:, 0] - mins[0]) / res).astype(np.int64)
    iy = ((points_2d[:, 1] - mins[1]) / res).astype(np.int64)
    cell_ids = ix.astype(np.int64) * 1_000_000 + iy.astype(np.int64)
    _, first_idx = np.unique(cell_ids, return_index=True)
    centers = np.stack(
        [mins[0] + (ix[first_idx] + 0.5) * res, mins[1] + (iy[first_idx] + 0.5) * res],
        axis=1,
    )
    return centers


def _dominant_manhattan_angle(points_2d: np.ndarray) -> float | None:
    """Hough-vote for the dominant wall direction, folded into [0, pi/2)."""
    grid, _ = _rasterize(points_2d)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grid = cv2.morphologyEx(grid, cv2.MORPH_CLOSE, kernel, iterations=1)

    max_dim = max(grid.shape)
    threshold = max(int(max_dim * MANHATTAN_HOUGH_VOTE_FRAC), MANHATTAN_HOUGH_MIN_VOTES)
    lines = cv2.HoughLines(grid, 1, np.pi / 360, threshold)
    if lines is None:
        return None

    thetas = lines[:, 0, 1]
    folded = np.mod(thetas, np.pi / 2)
    hist, edges = np.histogram(folded, bins=MANHATTAN_ANGLE_BINS, range=(0, np.pi / 2))
    if hist.max() == 0:
        return None
    peak = int(np.argmax(hist))
    return float((edges[peak] + edges[peak + 1]) / 2)


def _density_peak_1d(values: np.ndarray) -> tuple[float, float] | None:
    """Histogram mode of `values`; returns (center, sharpness) or None."""
    if len(values) < MIN_WALL_SUPPORT_POINTS:
        return None
    lo, hi = float(values.min()), float(values.max())
    span = hi - lo
    if span < WALL_DENSITY_BIN_M:
        return None
    n_bins = max(int(span / WALL_DENSITY_BIN_M), 3)
    counts, edges = np.histogram(values, bins=n_bins, range=(lo, hi))
    nonzero = counts[counts > 0]
    if len(nonzero) == 0:
        return None
    peak_idx = int(np.argmax(counts))
    mean_nonzero = float(np.mean(nonzero))
    sharpness = float(counts[peak_idx]) / mean_nonzero if mean_nonzero > 0 else 0.0
    center = float((edges[peak_idx] + edges[peak_idx + 1]) / 2)
    return center, sharpness


def _wall_peak_on_side(coords: np.ndarray, median: float, side: str) -> tuple[float, float] | None:
    """Density-peak wall position on one side of `median` along one axis.

    Searches only the outer WALL_SEARCH_HALF_FRAC of that half so the peak is
    found near the physical wall, not smeared across furniture-filled interior.
    """
    if side == "low":
        half = coords[coords <= median]
        if len(half) == 0:
            return None
        cutoff = np.percentile(half, WALL_SEARCH_HALF_FRAC * 100)
        search = half[half <= cutoff]
    else:
        half = coords[coords > median]
        if len(half) == 0:
            return None
        cutoff = np.percentile(half, (1 - WALL_SEARCH_HALF_FRAC) * 100)
        search = half[half >= cutoff]
    return _density_peak_1d(search)


def _pca_manhattan_angle(points_2d: np.ndarray) -> float:
    """Fallback wall angle from 2D PCA (largest-variance axis), folded to [0, pi/2)."""
    centered = points_2d - np.median(points_2d, axis=0)
    cov = np.cov(centered.T)
    vals, vecs = np.linalg.eigh(cov)
    axis = vecs[:, int(np.argmax(vals))]
    return float(np.arctan2(axis[1], axis[0]) % (np.pi / 2))


def _manhattan_rect_fit(points_2d: np.ndarray) -> WallFitResult | None:
    theta = _dominant_manhattan_angle(points_2d)
    if theta is None:
        # Sparse SfM clouds often fail Hough (thin wall traces); PCA orientation
        # still lets density-peak suppress doorway bleed.
        if len(points_2d) < MIN_WALL_SUPPORT_POINTS:
            return None
        theta = _pca_manhattan_angle(points_2d)

    cells = _occupied_cell_centers(points_2d)
    if len(cells) < MIN_WALL_SUPPORT_POINTS:
        return None

    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, s], [-s, c]])  # rotated = (cells - center) @ rot.T
    center = np.median(cells, axis=0)
    rotated = (cells - center) @ rot.T
    u, v = rotated[:, 0], rotated[:, 1]

    peaks = {}
    for axis_name, coords in (("u", u), ("v", v)):
        median = float(np.median(coords))
        lo_peak = _wall_peak_on_side(coords, median, "low")
        hi_peak = _wall_peak_on_side(coords, median, "high")
        if lo_peak is None or hi_peak is None:
            return None
        peaks[axis_name] = (lo_peak, hi_peak)

    (u_lo, u_lo_sharp), (u_hi, u_hi_sharp) = peaks["u"]
    (v_lo, v_lo_sharp), (v_hi, v_hi_sharp) = peaks["v"]
    if u_hi <= u_lo or v_hi <= v_lo:
        return None
    if min(u_lo_sharp, u_hi_sharp, v_lo_sharp, v_hi_sharp) < WALL_PEAK_MIN_SHARPNESS:
        return None  # no confident wall line on at least one side; let caller fall back

    corners_rot = np.array(
        [[u_lo, v_lo], [u_hi, v_lo], [u_hi, v_hi], [u_lo, v_hi]]
    )
    corners = corners_rot @ rot + center  # inverse of the forward rotation above

    area = _polygon_area(corners)
    if area < MIN_CONTOUR_AREA_M2:
        return None
    method = "manhattan_rect"
    if area > MAX_SINGLE_ROOM_AREA_M2:
        method = "manhattan_rect_large"

    return WallFitResult(
        vertices_2d=corners,
        method=method,
        floor_area_m2=area,
        shell_point_count=len(points_2d),
    )


def _polar_rect_fit(points_2d: np.ndarray) -> WallFitResult | None:
    outline = _polar_outline(points_2d)
    if len(outline) < MIN_OUTLINE_POINTS:
        return None

    rect = _oriented_rectangle(outline)
    rect_area = _polygon_area(rect)
    if rect_area < MIN_CONTOUR_AREA_M2:
        return None

    method = "oriented_rect"
    if rect_area > MAX_SINGLE_ROOM_AREA_M2:
        method = "oriented_rect_large"  # likely multi-space / doorway bleed

    return WallFitResult(
        vertices_2d=rect,
        method=method,
        floor_area_m2=rect_area,
        shell_point_count=len(outline),
    )


def fit_room_walls(points_2d: np.ndarray, *, method: str = "auto") -> WallFitResult | None:
    """method: "auto" (manhattan -> polar), "manhattan", or "polar"."""
    if len(points_2d) < 100:
        return None

    if method == "polar":
        return _polar_rect_fit(points_2d)
    if method == "manhattan":
        return _manhattan_rect_fit(points_2d)

    fit = _manhattan_rect_fit(points_2d)
    if fit is not None:
        return fit
    return _polar_rect_fit(points_2d)

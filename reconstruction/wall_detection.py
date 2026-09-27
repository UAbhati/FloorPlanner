"""Wall / room-polygon detection from a top-down wall-band point cloud.

History (see NOTES.md + memory.md):
- Convex hull of the full wall band over-includes interior clutter (~115 m² junk).
- Manhattan line-RANSAC produced invalid rectangles.
- Occupancy contour / minAreaRect on a radial shell still tracked the outer
  envelope of clutter + adjacent space seen through doorways.

Current approach — polar max-radius outline:
1. From the 2D median centre, bin points by angle; keep the farthest point in
   each bin (the wall hit along that ray).
2. Fit an oriented min-area rectangle to those outline points.
3. If that rectangle is implausible, fall back to the occupancy contour of the
   outline points; caller may still fall back to convex hull.
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


def fit_room_walls(points_2d: np.ndarray) -> WallFitResult | None:
    if len(points_2d) < 100:
        return None

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

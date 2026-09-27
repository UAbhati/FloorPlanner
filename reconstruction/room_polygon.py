"""Extract a top-down room polygon (walls + openings) from a wall-band point cloud.

Wall points live on the *interior surface* of the walls, so in a top-down
projection they trace the room's perimeter as a thin ring rather than filling
a solid area. Pipeline:

1. Project the wall-band point cloud (points between floor and ceiling, with a
   margin to exclude furniture/light-fixture clutter) onto the horizontal
   plane perpendicular to the up-axis found by `reconstruction.planes`.
2. Take the convex hull of the projected points and simplify it
   (`cv2.approxPolyDP`) down to a small polygon. This assumes a convex
   (typically rectangular) single room - a known limitation, see
   NOTES.md - and is the right amount of sophistication for a single-room
   LiDAR capture today; non-convex/multi-room layouts need a different
   approach (occupancy-grid line fitting) and are follow-up work.
3. Wall lengths are polygon edge lengths; floor area is the polygon area
   (shoelace formula, via shapely).
4. Openings are detected as gaps in point density along each wall: project
   the wall-band points onto each edge's line, bin by distance along the
   edge, and flag any contiguous low-density run (surrounded by high-density
   bins on both sides, so we don't flag the polygon's own corners) as an
   opening.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from shapely.geometry import Polygon

WALL_BAND_MARGIN_M = 0.15  # exclude this much near the floor and near the ceiling
HULL_SIMPLIFY_EPSILON_FRACTION = 0.02  # fraction of hull perimeter, for approxPolyDP
OPENING_BIN_SIZE_M = 0.05
OPENING_DENSITY_FRACTION = 0.15  # a bin below this fraction of the wall's median density is "open"
OPENING_MIN_WIDTH_M = 0.3
OPENING_MAX_WIDTH_M = 3.0
OPENING_EDGE_MARGIN_M = 0.1  # ignore low-density runs this close to a corner


@dataclass
class Wall:
    id: str
    start: np.ndarray  # (2,)
    end: np.ndarray  # (2,)
    length_m: float


@dataclass
class Opening:
    id: str
    wall_id: str
    position_on_wall_m: float
    width_m: float


@dataclass
class RoomPolygon:
    vertices_2d: np.ndarray  # (N, 2), in the horizontal-plane basis
    walls: list[Wall]
    openings: list[Opening] = field(default_factory=list)
    floor_area_m2: float = 0.0


def build_horizontal_basis(up_normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return two orthonormal axes spanning the plane perpendicular to up_normal."""
    up = up_normal / np.linalg.norm(up_normal)
    arbitrary = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u_axis = np.cross(up, arbitrary)
    u_axis /= np.linalg.norm(u_axis)
    v_axis = np.cross(up, u_axis)
    return u_axis, v_axis


def project_to_horizontal(points: np.ndarray, up_normal: np.ndarray) -> np.ndarray:
    """Project (N,3) world points onto the plane perpendicular to up_normal -> (N,2)."""
    u_axis, v_axis = build_horizontal_basis(up_normal)
    return np.stack([points @ u_axis, points @ v_axis], axis=1)


def extract_wall_band(
    points: np.ndarray,
    up_normal: np.ndarray,
    floor_offset: float,
    ceiling_offset: float,
    margin: float = WALL_BAND_MARGIN_M,
) -> np.ndarray:
    """Keep points strictly between floor+margin and ceiling-margin along up_normal."""
    up = up_normal / np.linalg.norm(up_normal)
    heights = points @ up
    lo = min(floor_offset, ceiling_offset) + margin
    hi = max(floor_offset, ceiling_offset) - margin
    if lo >= hi:
        raise ValueError(f"wall band is empty after margin: floor/ceiling too close ({lo} >= {hi})")
    return points[(heights >= lo) & (heights <= hi)]


def fit_room_polygon(points_2d: np.ndarray) -> np.ndarray:
    """Convex-hull + simplify the projected wall points into a room polygon (N,2)."""
    if len(points_2d) < 3:
        raise ValueError("not enough wall-band points to fit a polygon")

    hull = cv2.convexHull(points_2d.astype(np.float32))
    perimeter = cv2.arcLength(hull, closed=True)
    epsilon = HULL_SIMPLIFY_EPSILON_FRACTION * perimeter
    simplified = cv2.approxPolyDP(hull, epsilon, closed=True)
    return simplified.reshape(-1, 2)


def compute_walls(vertices_2d: np.ndarray) -> list[Wall]:
    walls = []
    n = len(vertices_2d)
    for i in range(n):
        start = vertices_2d[i]
        end = vertices_2d[(i + 1) % n]
        length = float(np.linalg.norm(end - start))
        walls.append(Wall(id=f"wall_{i}", start=start, end=end, length_m=length))
    return walls


def detect_openings_on_wall(wall: Wall, points_2d: np.ndarray, perpendicular_tolerance: float = 0.1) -> list[Opening]:
    """Find gaps in point density along one wall, from points near that wall's line."""
    edge_vec = wall.end - wall.start
    edge_len = np.linalg.norm(edge_vec)
    if edge_len < 1e-6:
        return []
    edge_dir = edge_vec / edge_len
    normal = np.array([-edge_dir[1], edge_dir[0]])

    rel = points_2d - wall.start
    along = rel @ edge_dir
    perp = rel @ normal

    near_wall = points_2d[(np.abs(perp) <= perpendicular_tolerance) & (along >= 0) & (along <= edge_len)]
    near_along = (near_wall - wall.start) @ edge_dir if len(near_wall) else np.array([])

    n_bins = max(int(edge_len / OPENING_BIN_SIZE_M), 1)
    counts, edges = np.histogram(near_along, bins=n_bins, range=(0, edge_len))
    if counts.sum() == 0:
        return []

    nonzero_median = np.median(counts[counts > 0]) if np.any(counts > 0) else 0
    threshold = max(nonzero_median * OPENING_DENSITY_FRACTION, 0.5)
    is_gap = counts < threshold

    openings = []
    opening_idx = 0
    i = 0
    while i < len(is_gap):
        if not is_gap[i]:
            i += 1
            continue
        j = i
        while j < len(is_gap) and is_gap[j]:
            j += 1
        gap_start_m = edges[i]
        gap_end_m = edges[j]
        width = gap_end_m - gap_start_m
        near_corner = gap_start_m < OPENING_EDGE_MARGIN_M or gap_end_m > edge_len - OPENING_EDGE_MARGIN_M
        if OPENING_MIN_WIDTH_M <= width <= OPENING_MAX_WIDTH_M and not near_corner:
            openings.append(
                Opening(
                    id=f"{wall.id}_opening_{opening_idx}",
                    wall_id=wall.id,
                    position_on_wall_m=float(gap_start_m),
                    width_m=float(width),
                )
            )
            opening_idx += 1
        i = j
    return openings


def build_room_polygon(wall_band_points_2d: np.ndarray) -> RoomPolygon:
    vertices = fit_room_polygon(wall_band_points_2d)
    walls = compute_walls(vertices)
    openings = []
    for wall in walls:
        openings.extend(detect_openings_on_wall(wall, wall_band_points_2d))
    area = Polygon(vertices).area
    return RoomPolygon(vertices_2d=vertices, walls=walls, openings=openings, floor_area_m2=area)

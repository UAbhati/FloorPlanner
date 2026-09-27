"""Extract a top-down room polygon (walls + openings) from a wall-band point cloud.

Pipeline:
1. Project wall-band points onto the horizontal plane (`planes` up-axis).
2. Prefer occupancy/outer-shell wall fit (`wall_detection.fit_room_walls`).
   Fall back to convex hull only when that returns None (flagged low-confidence).
3. Wall lengths = edge lengths; floor area via shapely.
4. Openings = low-density runs along each edge that are flanked by high-density
   bins (not just near-corner exclusions).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from shapely.geometry import Polygon

from reconstruction.wall_detection import fit_room_walls

WALL_BAND_MARGIN_M = 0.15  # exclude this much near the floor and near the ceiling
HULL_SIMPLIFY_EPSILON_FRACTION = 0.02  # fraction of hull perimeter, for approxPolyDP
OPENING_BIN_SIZE_M = 0.05
OPENING_DENSITY_FRACTION = 0.15  # a bin below this fraction of the wall's median density is "open"
OPENING_MIN_WIDTH_M = 0.3
OPENING_MAX_WIDTH_M = 3.0
OPENING_EDGE_MARGIN_M = 0.1  # ignore low-density runs this close to a corner
OPENING_PERP_TOLERANCE_M = 0.15  # how far from the wall line a point may sit


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
    method: str = "convex_hull"
    low_confidence: bool = False


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


def detect_openings_on_wall(
    wall: Wall,
    points_2d: np.ndarray,
    perpendicular_tolerance: float = OPENING_PERP_TOLERANCE_M,
) -> list[Opening]:
    """Find gaps in point density along one wall; require high-density flanks."""
    edge_vec = wall.end - wall.start
    edge_len = np.linalg.norm(edge_vec)
    if edge_len < 1e-6:
        return []
    edge_dir = edge_vec / edge_len
    normal = np.array([-edge_dir[1], edge_dir[0]])

    rel = points_2d - wall.start
    along = rel @ edge_dir
    perp = rel @ normal

    near_mask = (np.abs(perp) <= perpendicular_tolerance) & (along >= 0) & (along <= edge_len)
    near_along = along[near_mask]

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
        gap_start_m = float(edges[i])
        gap_end_m = float(edges[j])
        width = gap_end_m - gap_start_m
        near_corner = gap_start_m < OPENING_EDGE_MARGIN_M or gap_end_m > edge_len - OPENING_EDGE_MARGIN_M
        # Flanking bins must be high-density (real wall on both sides of the gap).
        left_ok = i > 0 and not is_gap[i - 1]
        right_ok = j < len(is_gap) and not is_gap[j]
        if (
            OPENING_MIN_WIDTH_M <= width <= OPENING_MAX_WIDTH_M
            and not near_corner
            and left_ok
            and right_ok
        ):
            openings.append(
                Opening(
                    id=f"{wall.id}_opening_{opening_idx}",
                    wall_id=wall.id,
                    position_on_wall_m=gap_start_m,
                    width_m=width,
                )
            )
            opening_idx += 1
        i = j
    return openings


def build_room_polygon(
    wall_band_points_2d: np.ndarray,
    *,
    method: str = "auto",
) -> RoomPolygon:
    """Build room polygon.

    method:
      - "auto": Manhattan density-peak fit -> polar oriented-rect fit -> hull fallback
      - "manhattan": Manhattan fit only; raises if fit returns None
      - "polar": polar max-radius fit only; raises if fit returns None
      - "hull": force convex hull (used for fix-loop *before* baseline)
    """
    if method == "hull":
        vertices = fit_room_polygon(wall_band_points_2d)
        chosen = "convex_hull"
        low_confidence = True
    else:
        fit_method = "auto" if method not in ("manhattan", "polar") else method
        fit = fit_room_walls(wall_band_points_2d, method=fit_method)
        if fit is not None:
            vertices = fit.vertices_2d
            chosen = fit.method
            low_confidence = fit.method.endswith("_large") or fit.floor_area_m2 > 40.0
        elif method in ("manhattan", "polar"):
            raise ValueError(f"{method} wall fit failed and method={method} forbids hull fallback")
        else:
            vertices = fit_room_polygon(wall_band_points_2d)
            chosen = "convex_hull"
            low_confidence = True

    walls = compute_walls(vertices)
    openings = []
    for wall in walls:
        openings.extend(detect_openings_on_wall(wall, wall_band_points_2d))
    area = float(Polygon(vertices).area)
    return RoomPolygon(
        vertices_2d=vertices,
        walls=walls,
        openings=openings,
        floor_area_m2=area,
        method=chosen,
        low_confidence=low_confidence,
    )

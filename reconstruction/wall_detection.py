"""Detect wall lines in the top-down wall-band point cloud and assemble a room polygon.

Diagnostic history (2026-09-27, see NOTES.md): plain convex-hull-of-wall-band
(reconstruction.room_polygon.fit_room_polygon) picks up furniture/clutter
mixed with real walls and gives an oversized, wrong-shaped polygon. Iterative
2D line RANSAC (skimage LineModelND) on the wall-band points was tried next:
on samples/single_scan_with_ceiling (a large, cluttered space) it found no
consistent direction - inlier fraction stayed low and dominant-line angles
were scattered across the full 0-180 degree range. On samples/single_room
(smaller, mostly eye-level coverage) a dominant direction did emerge
consistently around 45-49 degrees, though still noisy (~2-4% inlier
fraction per draw, echoing the floor's "multiple close parallel layers"
issue from planes.py).

What's implemented here: iterative line RANSAC on a random subsample (full
density is too slow and unnecessary for line fitting), merging nearby
parallel lines the same way planes.py merges floor sub-layers, then
classifying the merged lines into up to two roughly-perpendicular direction
groups (Manhattan-room assumption) and building a rectangle from the most-
supported line in each group. This only fires when both groups clear a
minimum-support bar; otherwise the caller should fall back to the convex
hull, since a wrong "confident" rectangle is worse than an honestly rough
hull. Non-rectangular rooms are not handled - documented limitation.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from skimage.measure import LineModelND, ransac

LINE_RESIDUAL_THRESHOLD_M = 0.04
LINE_MIN_INLIERS = 150
MAX_LINES_TO_EXTRACT = 20
LINE_SUBSAMPLE_SIZE = 20000
LINE_STRIP_MARGIN_M = 0.1
PARALLEL_MERGE_ANGLE_DEG = 12.0
PARALLEL_MERGE_OFFSET_M = 0.25
PERPENDICULAR_TOLERANCE_DEG = 20.0
MIN_GROUP_SUPPORT = 800  # summed inlier count required for each of the 2 direction groups


@dataclass
class WallLine:
    origin: np.ndarray  # (2,) a point on the line
    direction: np.ndarray  # (2,) unit direction
    inlier_count: int
    angle_deg: float  # in [0, 180)


def _fit_lines(points_2d: np.ndarray, rng: np.random.Generator) -> list[WallLine]:
    if len(points_2d) > LINE_SUBSAMPLE_SIZE:
        idx = rng.choice(len(points_2d), size=LINE_SUBSAMPLE_SIZE, replace=False)
        remaining = points_2d[idx].copy()
    else:
        remaining = points_2d.copy()

    lines = []
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        for _ in range(MAX_LINES_TO_EXTRACT):
            if len(remaining) < LINE_MIN_INLIERS:
                break
            model, inliers = ransac(
                remaining, LineModelND, min_samples=2, residual_threshold=LINE_RESIDUAL_THRESHOLD_M, max_trials=300
            )
            if inliers is None or inliers.sum() < LINE_MIN_INLIERS:
                break
            origin, direction = model.params
            direction = direction / np.linalg.norm(direction)
            angle = float(np.degrees(np.arctan2(direction[1], direction[0])) % 180)
            lines.append(WallLine(origin=origin, direction=direction, inlier_count=int(inliers.sum()), angle_deg=angle))

            distances = np.abs(model.residuals(remaining))
            remaining = remaining[distances > LINE_STRIP_MARGIN_M]
    return lines


def _angle_diff(a: float, b: float) -> float:
    """Smallest difference between two angles taken mod 180 degrees."""
    d = abs(a - b) % 180
    return min(d, 180 - d)


def _merge_parallel_lines(lines: list[WallLine]) -> list[WallLine]:
    """Merge lines that are close in both angle and perpendicular offset (same physical wall)."""
    merged: list[WallLine] = []
    used = [False] * len(lines)
    order = sorted(range(len(lines)), key=lambda i: -lines[i].inlier_count)
    for i in order:
        if used[i]:
            continue
        group = [lines[i]]
        used[i] = True
        ref = lines[i]
        ref_normal = np.array([-ref.direction[1], ref.direction[0]])
        for j in order:
            if used[j]:
                continue
            other = lines[j]
            if _angle_diff(ref.angle_deg, other.angle_deg) > PARALLEL_MERGE_ANGLE_DEG:
                continue
            offset_diff = abs(np.dot(other.origin - ref.origin, ref_normal))
            if offset_diff <= PARALLEL_MERGE_OFFSET_M:
                group.append(other)
                used[j] = True

        total = sum(w.inlier_count for w in group)
        avg_angle = float(np.average([w.angle_deg for w in group], weights=[w.inlier_count for w in group]))
        avg_origin = np.average([w.origin for w in group], axis=0, weights=[w.inlier_count for w in group])
        direction = np.array([np.cos(np.radians(avg_angle)), np.sin(np.radians(avg_angle))])
        merged.append(WallLine(origin=avg_origin, direction=direction, inlier_count=total, angle_deg=avg_angle))

    merged.sort(key=lambda w: -w.inlier_count)
    return merged


def _line_intersection(a: WallLine, b: WallLine) -> np.ndarray | None:
    """Intersection point of two 2D lines given as (origin, direction), or None if near-parallel."""
    d1, d2 = a.direction, b.direction
    denom = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(denom) < 1e-9:
        return None
    diff = b.origin - a.origin
    t = (diff[0] * d2[1] - diff[1] * d2[0]) / denom
    return a.origin + t * d1


def fit_rectangular_room(points_2d: np.ndarray, seed: int = 42) -> np.ndarray | None:
    """Try to fit a 4-corner rectangle from two dominant perpendicular wall directions.

    Returns None (caller should fall back to the convex hull) if no two
    perpendicular direction groups clear MIN_GROUP_SUPPORT.
    """
    rng = np.random.default_rng(seed)
    lines = _fit_lines(points_2d, rng)
    if len(lines) < 2:
        return None
    merged = _merge_parallel_lines(lines)

    primary = merged[0]
    group_a = [w for w in merged if _angle_diff(w.angle_deg, primary.angle_deg) <= PERPENDICULAR_TOLERANCE_DEG]
    group_b = [
        w
        for w in merged
        if abs(_angle_diff(w.angle_deg, primary.angle_deg) - 90) <= PERPENDICULAR_TOLERANCE_DEG
    ]
    support_a = sum(w.inlier_count for w in group_a)
    support_b = sum(w.inlier_count for w in group_b)
    if support_a < MIN_GROUP_SUPPORT or support_b < MIN_GROUP_SUPPORT or not group_b:
        return None

    # Within each direction group, the two walls of the room are the most
    # widely separated (by perpendicular offset), not necessarily the two
    # single highest-inlier lines (a hallway-facing wall might outscore the
    # true opposite wall while still being the *same* wall as another entry).
    def extreme_pair(group: list[WallLine], ref_direction: np.ndarray) -> tuple[WallLine, WallLine]:
        normal = np.array([-ref_direction[1], ref_direction[0]])
        by_offset = sorted(group, key=lambda w: np.dot(w.origin, normal))
        return by_offset[0], by_offset[-1]

    a_lo, a_hi = extreme_pair(group_a, primary.direction)
    b_lo, b_hi = extreme_pair(group_b, group_b[0].direction)

    corners = [
        _line_intersection(a_lo, b_lo),
        _line_intersection(a_lo, b_hi),
        _line_intersection(a_hi, b_hi),
        _line_intersection(a_hi, b_lo),
    ]
    if any(c is None for c in corners):
        return None
    return np.array(corners)

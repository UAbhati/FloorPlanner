"""Detect floor/ceiling planes and derive ceiling height.

Three approaches were tried, in order, on samples/single_room and
samples/single_scan_with_ceiling (see NOTES.md for the full story):

1. Histogram peak search on a candidate up-axis. Failed: a handheld walk
   views floor/ceiling from many angles/distances, so wall points spread
   continuously across the whole height range and bury any floor/ceiling
   excess in a broad unimodal hump - no clean bimodal peak on any axis.
2. Iterative RANSAC plane extraction (peel off the largest plane, strip a
   slab around it, repeat), then cluster the resulting planes by normal
   direction and offset gap, picking the lowest/highest significant cluster
   as floor/ceiling. Failed: grazing-incidence LiDAR noise makes the floor
   (and, on the denser sample, the ceiling too) come back as several
   RANSAC-stochastic sub-planes 10-30cm apart. Single-linkage gap-clustering
   chains through those gaps transitively and merges floor, mid-height
   clutter, and ceiling into one giant "cluster" spanning the whole room
   height - exactly the failure it was meant to prevent.
3. What's implemented below: fit the floor as a single RANSAC plane on the
   *whole* cloud (the floor is reliably the single largest flat surface in
   an indoor scan - confirmed empirically, it wins the very first RANSAC
   draw on both samples), derive the up-axis from its normal, then restrict
   the ceiling search to points with a physically-motivated minimum
   clearance above the floor (CEILING_MIN_CLEARANCE_M) before fitting a
   second single RANSAC plane there. This sidesteps both failure modes:
   no need to separate multiple candidate peaks/clusters at all, because
   the clearance filter already removes furniture/mid-height clutter before
   the ceiling fit ever sees it. RANSAC is seeded (RANSAC_SEED) for
   run-to-run determinism, which the repeatability gate depends on.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import open3d as o3d

RANSAC_DISTANCE_THRESHOLD_M = 0.02
RANSAC_SEED = 42  # fixed for run-to-run determinism (the repeatability gate depends on it)
MIN_PLANE_INLIERS = 500
NORMAL_PARALLEL_COS_THRESHOLD = 0.9  # ~25 degrees, used to sanity-check the ceiling normal against the floor's
CEILING_MIN_CLEARANCE_M = 1.8  # exclude furniture/mid-height clutter before fitting the ceiling plane


@dataclass
class PlaneFit:
    normal: np.ndarray  # (3,) unit normal
    offset: float  # signed distance of the plane from the origin along `normal`
    inlier_count: int
    residual_std_m: float


def _fit_single_plane(points: np.ndarray) -> PlaneFit:
    if len(points) < MIN_PLANE_INLIERS:
        raise ValueError(f"only {len(points)} points available, need >= {MIN_PLANE_INLIERS} to fit a plane")

    o3d.utility.random.seed(RANSAC_SEED)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    plane_model, inlier_idx = pcd.segment_plane(
        distance_threshold=RANSAC_DISTANCE_THRESHOLD_M, ransac_n=3, num_iterations=1000
    )
    if len(inlier_idx) < MIN_PLANE_INLIERS:
        raise ValueError(f"best plane only had {len(inlier_idx)} inliers, need >= {MIN_PLANE_INLIERS}")

    a, b, c, d = plane_model
    normal = np.array([a, b, c])
    norm_len = np.linalg.norm(normal)
    normal = normal / norm_len
    offset = -d / norm_len

    inlier_pts = points[inlier_idx]
    distances = np.abs(inlier_pts @ normal - offset)
    return PlaneFit(normal=normal, offset=offset, inlier_count=len(inlier_idx), residual_std_m=float(np.std(distances)))


@dataclass
class FloorCeilingResult:
    up_normal: np.ndarray
    floor: PlaneFit
    ceiling: PlaneFit


def find_floor_and_ceiling(points: np.ndarray) -> FloorCeilingResult:
    floor = _fit_single_plane(points)

    # Orient the normal so "up" points toward the majority of the remaining
    # points (the floor should have most of the room's volume above it, not
    # below - this also fixes the arbitrary sign RANSAC returns).
    heights = points @ floor.normal
    above = np.sum(heights > floor.offset)
    below = np.sum(heights < floor.offset)
    up_normal = floor.normal if above >= below else -floor.normal
    floor_offset = float(np.dot(floor.normal, up_normal)) * floor.offset

    ceiling_candidates = points[points @ up_normal > floor_offset + CEILING_MIN_CLEARANCE_M]
    if len(ceiling_candidates) < MIN_PLANE_INLIERS:
        raise ValueError(
            f"only {len(ceiling_candidates)} points above floor+{CEILING_MIN_CLEARANCE_M}m - "
            "capture likely doesn't cover the ceiling"
        )

    ceiling = _fit_single_plane(ceiling_candidates)
    cos_angle = abs(float(np.dot(ceiling.normal, up_normal)))
    if cos_angle < NORMAL_PARALLEL_COS_THRESHOLD:
        raise ValueError(
            f"best plane above floor+{CEILING_MIN_CLEARANCE_M}m isn't parallel to the floor "
            f"(cos angle {cos_angle:.2f} < {NORMAL_PARALLEL_COS_THRESHOLD}) - likely a wall or clutter, not a ceiling"
        )

    # Re-express with a consistent sign/offset along up_normal.
    floor_fit = PlaneFit(normal=up_normal, offset=floor_offset, inlier_count=floor.inlier_count, residual_std_m=floor.residual_std_m)
    ceiling_offset = float(np.dot(ceiling.normal, up_normal)) * ceiling.offset
    ceiling_fit = PlaneFit(normal=up_normal, offset=ceiling_offset, inlier_count=ceiling.inlier_count, residual_std_m=ceiling.residual_std_m)

    return FloorCeilingResult(up_normal=up_normal, floor=floor_fit, ceiling=ceiling_fit)


def ceiling_height_measurement(points: np.ndarray, confidence_level: float = 0.95) -> dict:
    """Return a schema-shaped `measurement` dict for ceiling height."""
    result = find_floor_and_ceiling(points)
    height = abs(result.ceiling.offset - result.floor.offset)

    sigma = float(np.sqrt(result.floor.residual_std_m**2 + result.ceiling.residual_std_m**2))
    z = 1.96 if confidence_level == 0.95 else 1.0
    margin = z * sigma

    return {
        "value_m": height,
        "ci_low_m": height - margin,
        "ci_high_m": height + margin,
        "confidence_level": confidence_level,
        "_debug": {
            "up_normal": result.up_normal.tolist(),
            "floor_offset": result.floor.offset,
            "ceiling_offset": result.ceiling.offset,
            "floor_inliers": result.floor.inlier_count,
            "ceiling_inliers": result.ceiling.inlier_count,
        },
    }

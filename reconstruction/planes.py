"""Detect floor/ceiling planes and derive ceiling height via iterative RANSAC.

A simple 1D histogram of point coordinates along a candidate "up" axis turned
out not to show clean floor/ceiling peaks on the sample capture: a handheld
walk views floor/ceiling from many angles and distances, and wall points
spread continuously across the height range, burying any floor/ceiling excess
in a broad unimodal hump (see git history for the earlier histogram-peak
attempt and the diagnostic plots that ruled it out).

Approach used instead, the standard one for this kind of indoor point cloud:
1. Iteratively RANSAC-fit the largest plane in the cloud (open3d segment_plane),
   strip a slab of points around it (not just its tight RANSAC inliers - see
   SLAB_STRIP_MARGIN_M), and repeat, collecting the top-N planes by inlier
   count. Stripping only the exact inliers was tried first and failed: grazing-
   incidence LiDAR noise on the floor is thick enough that RANSAC re-fits
   several near-parallel "layers" of the same physical floor before ever
   reaching the ceiling, so a wider slab has to be removed per plane.
2. Group planes whose normals are nearly parallel (dot product close to +-1):
   the group with the most total inliers is the dominant "horizontal" family,
   and its shared normal direction is the up axis (not necessarily a coordinate
   axis in general, though for gravity-aligned ARKit poses it should be close
   to one).
3. Within that family, the plane with the lowest signed position along the
   normal is the floor, the highest is the ceiling.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import open3d as o3d

RANSAC_DISTANCE_THRESHOLD_M = 0.02
SLAB_STRIP_MARGIN_M = 0.08  # remove a slab this wide around each fitted plane, not just its tight inliers
MAX_PLANES_TO_EXTRACT = 12
MIN_PLANE_INLIERS = 500
NORMAL_PARALLEL_COS_THRESHOLD = 0.9  # ~25 degrees
MIN_FLOOR_CEILING_GAP_M = 1.5  # reject a "ceiling" implausibly close to the floor


@dataclass
class PlaneFit:
    normal: np.ndarray  # (3,) unit normal
    offset: float  # signed distance of the plane from the origin along `normal`
    inlier_count: int
    residual_std_m: float
    points: np.ndarray  # inlier points, for downstream footprint extraction


def _extract_top_planes(points: np.ndarray, max_planes: int = MAX_PLANES_TO_EXTRACT) -> list[PlaneFit]:
    remaining = points.copy()
    planes = []
    for _ in range(max_planes):
        if len(remaining) < MIN_PLANE_INLIERS:
            break
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(remaining)
        plane_model, inlier_idx = pcd.segment_plane(
            distance_threshold=RANSAC_DISTANCE_THRESHOLD_M, ransac_n=3, num_iterations=1000
        )
        if len(inlier_idx) < MIN_PLANE_INLIERS:
            break
        a, b, c, d = plane_model
        normal = np.array([a, b, c])
        norm_len = np.linalg.norm(normal)
        normal = normal / norm_len
        offset = -d / norm_len

        inlier_pts = remaining[inlier_idx]
        distances = np.abs(inlier_pts @ normal - offset)
        planes.append(
            PlaneFit(
                normal=normal,
                offset=offset,
                inlier_count=len(inlier_idx),
                residual_std_m=float(np.std(distances)),
                points=inlier_pts,
            )
        )
        # Strip a slab around the whole plane, not just its tight RANSAC
        # inliers, so noisy points belonging to the same physical surface
        # don't get re-fit as spurious extra "planes" next iteration.
        all_distances = np.abs(remaining @ normal - offset)
        remaining = remaining[all_distances > SLAB_STRIP_MARGIN_M]
    return planes


def _group_parallel_planes(planes: list[PlaneFit]) -> list[list[PlaneFit]]:
    groups: list[list[PlaneFit]] = []
    for plane in planes:
        placed = False
        for group in groups:
            ref = group[0]
            cos_angle = abs(float(np.dot(plane.normal, ref.normal)))
            if cos_angle >= NORMAL_PARALLEL_COS_THRESHOLD:
                group.append(plane)
                placed = True
                break
        if not placed:
            groups.append([plane])
    return groups


@dataclass
class FloorCeilingResult:
    up_normal: np.ndarray
    floor: PlaneFit
    ceiling: PlaneFit


def find_floor_and_ceiling(points: np.ndarray) -> FloorCeilingResult:
    planes = _extract_top_planes(points)
    if len(planes) < 2:
        raise ValueError(f"only found {len(planes)} planes with >= {MIN_PLANE_INLIERS} inliers")

    groups = _group_parallel_planes(planes)
    groups.sort(key=lambda g: -sum(p.inlier_count for p in g))

    for group in groups:
        if len(group) < 2:
            continue
        ref_normal = group[0].normal
        # Signed offset consistently oriented along the reference normal.
        signed = []
        for p in group:
            sign = 1.0 if np.dot(p.normal, ref_normal) >= 0 else -1.0
            signed.append((sign * p.offset, p))
        signed.sort(key=lambda t: t[0])
        lowest_offset, lowest_plane = signed[0]
        highest_offset, highest_plane = signed[-1]
        if highest_offset - lowest_offset >= MIN_FLOOR_CEILING_GAP_M:
            return FloorCeilingResult(up_normal=ref_normal, floor=lowest_plane, ceiling=highest_plane)

    raise ValueError(
        "no parallel-plane group had two members at least "
        f"{MIN_FLOOR_CEILING_GAP_M} m apart (checked {len(groups)} groups from {len(planes)} planes)"
    )


def ceiling_height_measurement(points: np.ndarray, confidence_level: float = 0.95) -> dict:
    """Return a schema-shaped `measurement` dict for ceiling height."""
    result = find_floor_and_ceiling(points)
    floor_offset = float(np.dot(result.floor.normal, result.up_normal)) * result.floor.offset
    ceiling_offset = float(np.dot(result.ceiling.normal, result.up_normal)) * result.ceiling.offset
    height = abs(ceiling_offset - floor_offset)

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
            "floor_offset": floor_offset,
            "ceiling_offset": ceiling_offset,
            "floor_inliers": result.floor.inlier_count,
            "ceiling_inliers": result.ceiling.inlier_count,
        },
    }

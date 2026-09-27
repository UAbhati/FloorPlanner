"""Back-project Stray Scanner depth+confidence frames into a world-space point cloud.

Camera convention: ARKit camera space is X-right, Y-up, Z-backward (the camera
looks down -Z), and ARKit's depth buffer stores distance along -Z, perpendicular
to the image plane. Standard pinhole back-projection for that convention, with
image row v measured top-to-bottom:

    x_cam =  (u - cx) * depth / fx
    y_cam = -(v - cy) * depth / fy
    z_cam = -depth

World points are then camera_to_world @ [x_cam, y_cam, z_cam, 1], using the
odometry pose's quaternion (also in ARKit's world convention), so poses and
back-projected points are internally consistent even if the absolute
axis-to-gravity mapping is only established later, in reconstruction/planes.py.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

from capture_io.stray_scanner import FramePose, StrayCapture


def backproject_frame(
    capture: StrayCapture,
    pose: FramePose,
    min_confidence: int = 2,
    pixel_stride: int = 1,
) -> np.ndarray:
    """Return an (N, 3) array of world-space points for one frame.

    pixel_stride > 1 subsamples the depth grid for speed (e.g. stride=2 keeps
    1/4 of the pixels).
    """
    depth_mm = capture.load_depth_mm(pose.frame_index)
    confidence = capture.load_confidence(pose.frame_index)
    fx, fy, cx, cy = capture.depth_intrinsics(pose)

    depth_mm = depth_mm[::pixel_stride, ::pixel_stride]
    confidence = confidence[::pixel_stride, ::pixel_stride]

    h, w = depth_mm.shape
    mask = (confidence >= min_confidence) & (depth_mm > 0)
    if not np.any(mask):
        return np.empty((0, 3))

    v_idx, u_idx = np.nonzero(mask)
    # Undo the stride so pixel coordinates map back to the original intrinsics grid.
    u = u_idx * pixel_stride
    v = v_idx * pixel_stride
    depth_m = depth_mm[v_idx, u_idx].astype(np.float64) / 1000.0

    x_cam = (u - cx) * depth_m / fx
    y_cam = -(v - cy) * depth_m / fy
    z_cam = -depth_m

    cam_points = np.stack([x_cam, y_cam, z_cam, np.ones_like(x_cam)], axis=1)
    world_points = (pose.camera_to_world() @ cam_points.T).T
    return world_points[:, :3]


def build_point_cloud(
    capture: StrayCapture,
    frame_stride: int = 10,
    pixel_stride: int = 2,
    min_confidence: int = 2,
    voxel_size: float = 0.02,
) -> o3d.geometry.PointCloud:
    """Aggregate back-projected points across a subsample of frames into one cloud.

    frame_stride/pixel_stride trade completeness for speed; voxel_size (metres)
    downsamples the aggregated cloud to bound memory/runtime regardless of
    capture length.
    """
    all_points = []
    for pose in capture.poses[::frame_stride]:
        pts = backproject_frame(capture, pose, min_confidence=min_confidence, pixel_stride=pixel_stride)
        if pts.size:
            all_points.append(pts)

    if not all_points:
        raise ValueError("no points survived back-projection and confidence filtering")

    points = np.concatenate(all_points, axis=0)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    if voxel_size > 0:
        pcd = pcd.voxel_down_sample(voxel_size)
    return pcd

"""Loader for the Stray Scanner (Stray Robots) capture format.

Directory layout produced by the app:
    camera_matrix.csv   3x3 RGB intrinsics (one matrix for the whole capture)
    imu.csv             timestamp, a_x, a_y, a_z, alpha_x, alpha_y, alpha_z
    odometry.csv        timestamp, frame, x, y, z, qx, qy, qz, qw,
                         fx, fy, cx, cy, distortion_center_x, distortion_center_y
                         (pose + per-frame RGB-space intrinsics, ARKit world frame,
                         quaternion in xyzw order)
    rgb.mp4             RGB video, one frame per odometry row
    depth/NNNNNN.png    uint16 depth in millimetres, one per RGB frame, lower
                         resolution than the RGB video (e.g. 256x192 vs 1920x1440)
    confidence/NNNNNN.png  uint8 confidence in {0, 1, 2} (low/medium/high),
                         same resolution and pixel grid as depth/

Confirmed against the "Single Room Assignment" sample (2026-09-27):
    depth values ~500-1700 (mm), confidence values exactly {0, 1, 2},
    1 odometry row per RGB frame, frame count == depth/confidence PNG count.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class FramePose:
    """One odometry row: world-frame pose plus this frame's RGB-space intrinsics."""

    frame_index: int
    timestamp: float
    position: np.ndarray  # (3,) x, y, z in ARKit world coordinates, metres
    quaternion_xyzw: np.ndarray  # (4,) qx, qy, qz, qw
    fx: float
    fy: float
    cx: float
    cy: float

    def rotation_matrix(self) -> np.ndarray:
        """3x3 rotation matrix from the xyzw quaternion (camera-to-world)."""
        x, y, z, w = self.quaternion_xyzw
        return np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )

    def camera_to_world(self) -> np.ndarray:
        """4x4 homogeneous camera-to-world transform."""
        T = np.eye(4)
        T[:3, :3] = self.rotation_matrix()
        T[:3, 3] = self.position
        return T


@dataclass
class StrayCapture:
    root: Path
    camera_matrix: np.ndarray  # (3,3) intrinsics for the RGB video's native resolution
    poses: list[FramePose]
    rgb_width: int
    rgb_height: int

    def depth_path(self, frame_index: int) -> Path:
        return self.root / "depth" / f"{frame_index:06d}.png"

    def confidence_path(self, frame_index: int) -> Path:
        return self.root / "confidence" / f"{frame_index:06d}.png"

    def rgb_video_path(self) -> Path:
        return self.root / "rgb.mp4"

    def load_depth_mm(self, frame_index: int) -> np.ndarray:
        """uint16 depth map in millimetres, at depth-native resolution."""
        arr = np.array(Image.open(self.depth_path(frame_index)))
        if arr.dtype != np.uint16:
            raise ValueError(
                f"expected uint16 depth PNG at frame {frame_index}, got {arr.dtype}"
            )
        return arr

    def load_confidence(self, frame_index: int) -> np.ndarray:
        """uint8 confidence map in {0,1,2}, same grid as depth."""
        arr = np.array(Image.open(self.confidence_path(frame_index)))
        if arr.dtype != np.uint8:
            raise ValueError(
                f"expected uint8 confidence PNG at frame {frame_index}, got {arr.dtype}"
            )
        return arr

    def depth_intrinsics(self, pose: FramePose) -> tuple[float, float, float, float]:
        """Scale this frame's RGB-space intrinsics down to the depth map's resolution.

        Stray Scanner's depth/confidence PNGs are a fixed lower resolution than the
        RGB video but share the same field of view, so intrinsics scale by the
        width/height ratio.
        """
        sample_depth = self.load_depth_mm(pose.frame_index)
        depth_h, depth_w = sample_depth.shape
        sx = depth_w / self.rgb_width
        sy = depth_h / self.rgb_height
        return pose.fx * sx, pose.fy * sy, pose.cx * sx, pose.cy * sy

    def num_frames(self) -> int:
        return len(self.poses)


def _parse_camera_matrix(path: Path) -> np.ndarray:
    rows = []
    with open(path, newline="") as f:
        for row in csv.reader(f):
            rows.append([float(v) for v in row if v.strip() != ""])
    matrix = np.array(rows, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError(f"expected a 3x3 camera matrix in {path}, got shape {matrix.shape}")
    return matrix


def _parse_odometry(path: Path) -> list[FramePose]:
    poses = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if "frame" not in header[1]:
            raise ValueError(f"unexpected odometry.csv header: {header}")
        for row in reader:
            if not row or not row[0].strip():
                continue
            timestamp = float(row[0])
            frame_index = int(row[1])
            x, y, z = (float(v) for v in row[2:5])
            qx, qy, qz, qw = (float(v) for v in row[5:9])
            fx, fy, cx, cy = (float(v) for v in row[9:13])
            poses.append(
                FramePose(
                    frame_index=frame_index,
                    timestamp=timestamp,
                    position=np.array([x, y, z]),
                    quaternion_xyzw=np.array([qx, qy, qz, qw]),
                    fx=fx,
                    fy=fy,
                    cx=cx,
                    cy=cy,
                )
            )
    return poses


def _probe_rgb_resolution(video_path: Path) -> tuple[int, int]:
    """Read width/height from rgb.mp4 via ffprobe, no extra Python deps."""
    import json
    import subprocess

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)["streams"][0]
    return int(info["width"]), int(info["height"])


def load_stray_capture(root: str | Path) -> StrayCapture:
    root = Path(root)
    camera_matrix = _parse_camera_matrix(root / "camera_matrix.csv")
    poses = _parse_odometry(root / "odometry.csv")
    rgb_width, rgb_height = _probe_rgb_resolution(root / "rgb.mp4")

    depth_count = len(list((root / "depth").glob("*.png")))
    confidence_count = len(list((root / "confidence").glob("*.png")))
    if not (len(poses) == depth_count == confidence_count):
        raise ValueError(
            f"frame count mismatch in {root}: "
            f"{len(poses)} odometry rows, {depth_count} depth PNGs, "
            f"{confidence_count} confidence PNGs"
        )

    return StrayCapture(
        root=root,
        camera_matrix=camera_matrix,
        poses=poses,
        rgb_width=rgb_width,
        rgb_height=rgb_height,
    )

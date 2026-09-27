"""Run COLMAP SfM on a photo set and return a metric-scaled 3D point cloud.

Pipeline (COLMAP CLI 3.x/4.x):
  feature_extractor → exhaustive_matcher → mapper → model_converter (TXT)

Metric scale is recovered by fitting the same polar/oriented-rect room polygon
used on LiDAR, then scaling so the longer wall matches ``ref_length_m``.

If COLMAP fails (too few images, no GPU, degenerate motion), raises
``SfMError`` so the caller can fall back to the ref-rectangle path.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reconstruction.planes import find_floor, find_floor_and_ceiling, rough_height_above_floor
from reconstruction.room_polygon import (
    RoomPolygon,
    build_room_polygon,
    extract_wall_band,
    project_to_horizontal,
)


class SfMError(RuntimeError):
    pass


@dataclass
class SfMResult:
    points: np.ndarray  # (N, 3) metric world points after scale
    room: RoomPolygon
    ceiling_height_m: float | None
    ceiling_source: str  # "plane" | "rough" | "none"
    scale: float
    num_points: int
    workspace: Path
    notes: str


def _run(cmd: list[str], cwd: Path | None = None, *, allow_fail: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0 and not allow_fail:
        raise SfMError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    return proc


def _ensure_colmap() -> str:
    path = shutil.which("colmap")
    if not path:
        raise SfMError("colmap not found on PATH (brew install colmap)")
    return path


def _stage_images(image_paths: list[Path], image_dir: Path) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    for i, src in enumerate(image_paths):
        # COLMAP is happier with simple extensions; re-encode jpeg if needed via copy.
        dst = image_dir / f"img_{i:04d}{src.suffix.lower()}"
        if dst.suffix not in {".jpg", ".jpeg", ".png"}:
            dst = image_dir / f"img_{i:04d}.jpg"
            # Let ffmpeg convert exotic formats; for jpeg just copy.
            if src.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                shutil.copy2(src, dst)
            else:
                _run(["ffmpeg", "-y", "-i", str(src), str(dst)])
        else:
            if not dst.exists():
                shutil.copy2(src, dst)
        staged.append(dst)
    if len(staged) < 3:
        raise SfMError(f"need >= 3 images for SfM, got {len(staged)}")
    return staged


def _parse_points3d_txt(path: Path) -> np.ndarray:
    """Parse COLMAP points3D.txt → (N,3) XYZ."""
    pts = []
    with open(path) as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            # POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]
            if len(parts) < 4:
                continue
            pts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if len(pts) < 30:
        raise SfMError(f"too few reconstructed points ({len(pts)}) in {path}")
    return np.asarray(pts, dtype=np.float64)


def run_colmap(image_paths: list[Path], workspace: Path) -> np.ndarray:
    """Run COLMAP and return sparse XYZ points (arbitrary scale)."""
    colmap = _ensure_colmap()
    workspace.mkdir(parents=True, exist_ok=True)
    image_dir = workspace / "images"
    db_path = workspace / "database.db"
    sparse_dir = workspace / "sparse"
    sparse_dir.mkdir(exist_ok=True)

    # Reuse a previous successful model in this workspace when present.
    existing = sparse_dir / "0" / "points3D.txt"
    if existing.is_file():
        try:
            return _parse_points3d_txt(existing)
        except SfMError:
            pass

    _stage_images(image_paths, image_dir)

    if db_path.exists():
        db_path.unlink()

    _run(
        [
            colmap,
            "feature_extractor",
            "--database_path",
            str(db_path),
            "--image_path",
            str(image_dir),
            "--ImageReader.single_camera",
            "1",
            "--FeatureExtraction.use_gpu",
            "0",
        ]
    )
    _run(
        [
            colmap,
            "exhaustive_matcher",
            "--database_path",
            str(db_path),
            "--FeatureMatching.use_gpu",
            "0",
        ]
    )
    _run(
        [
            colmap,
            "mapper",
            "--database_path",
            str(db_path),
            "--image_path",
            str(image_dir),
            "--output_path",
            str(sparse_dir),
            # Indoor handheld video often has weak parallax — relax init gates.
            "--Mapper.init_min_num_inliers",
            "50",
            "--Mapper.init_min_tri_angle",
            "4",
            "--Mapper.abs_pose_min_num_inliers",
            "15",
            "--Mapper.abs_pose_min_inlier_ratio",
            "0.15",
        ],
        allow_fail=True,
    )

    candidates = []
    model_0 = sparse_dir / "0"
    if model_0.is_dir():
        candidates.append(model_0)
    candidates.extend(sorted(p for p in sparse_dir.iterdir() if p.is_dir() and p.name != "0"))
    if not candidates:
        raise SfMError(f"COLMAP mapper produced no models under {sparse_dir}")

    last_err: Exception | None = None
    for cand in candidates:
        try:
            _run(
                [
                    colmap,
                    "model_converter",
                    "--input_path",
                    str(cand),
                    "--output_path",
                    str(cand),
                    "--output_type",
                    "TXT",
                ]
            )
            return _parse_points3d_txt(cand / "points3D.txt")
        except (SfMError, FileNotFoundError) as exc:
            last_err = exc
            continue
    raise SfMError(f"no usable COLMAP model under {sparse_dir}: {last_err}")


def _pca_up_axis(points: np.ndarray) -> np.ndarray:
    """Smallest-variance PCA axis as a gravity/up prior for sparse clouds."""
    centered = points - points.mean(axis=0)
    cov = centered.T @ centered / max(len(points) - 1, 1)
    vals, vecs = np.linalg.eigh(cov)
    up = vecs[:, 0]  # smallest eigenvalue
    # Orient so more points lie above the median plane.
    if np.median(points @ up) < np.mean(points @ up):
        # Prefer the direction where the upper half has more extent? Use: majority above median.
        pass
    heights = points @ up
    if np.sum(heights > np.median(heights)) < len(points) / 2:
        up = -up
    return up / np.linalg.norm(up)


def reconstruct_metric_room(
    image_paths: list[Path],
    workspace: Path,
    ref_length_m: float,
) -> SfMResult:
    """SfM → floor/ceiling → room polygon, scaled so longest wall = ref_length_m."""
    try:
        points = run_colmap(image_paths, workspace)
    except SfMError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any COLMAP/parse failure to caller
        raise SfMError(str(exc)) from exc

    med = np.median(points, axis=0)
    mad = np.median(np.abs(points - med), axis=0) + 1e-6
    keep = np.all(np.abs(points - med) < 10 * mad, axis=1)
    points = points[keep]
    if len(points) < 200:
        raise SfMError(
            f"sparse reconstruction too thin ({len(points)} pts); "
            "need more overlapping views (or use --no-colmap / denser video frames)"
        )

    notes = [f"colmap_points={len(points)}"]
    ceiling_height_m: float | None = None
    ceiling_source = "none"

    try:
        if len(points) >= 500:
            fc = find_floor_and_ceiling(points)
            up = fc.up_normal
            floor_off, ceil_off = fc.floor.offset, fc.ceiling.offset
            ceiling_height_m = abs(ceil_off - floor_off)
            ceiling_source = "plane"
            wall_band = extract_wall_band(points, up, floor_off, ceil_off)
        else:
            notes.append("sparse_pca_up")
            up = _pca_up_axis(points)
            heights = points @ up
            floor_off = float(np.percentile(heights, 10))
            ceil_off = float(np.percentile(heights, 90))
            ceiling_height_m = abs(ceil_off - floor_off)
            ceiling_source = "rough"
            lo = floor_off + 0.05 * (ceil_off - floor_off)
            hi = ceil_off - 0.05 * (ceil_off - floor_off)
            wall_band = points[(heights >= lo) & (heights <= hi)]
    except Exception as exc:  # noqa: BLE001
        raise SfMError(f"plane/wall-band failed: {exc}") from exc

    if len(wall_band) < 50:
        raise SfMError(f"wall band too thin ({len(wall_band)} points)")

    pts2d = project_to_horizontal(wall_band, up)
    room = build_room_polygon(pts2d)
    lengths = sorted((w.length_m for w in room.walls), reverse=True)
    long_wall = lengths[0] if lengths else 0.0
    if long_wall < 1e-3:
        raise SfMError("degenerate room polygon from SfM points")

    scale = ref_length_m / long_wall
    points_m = points * scale
    room.vertices_2d = room.vertices_2d * scale
    for wall in room.walls:
        wall.start = wall.start * scale
        wall.end = wall.end * scale
        wall.length_m *= scale
    for opening in room.openings:
        opening.width_m *= scale
        opening.position_on_wall_m *= scale
    room.floor_area_m2 *= scale * scale
    room.method = f"colmap_{room.method}"
    room.low_confidence = True

    if ceiling_height_m is not None:
        ceiling_height_m *= scale
        if not (1.7 <= ceiling_height_m <= 4.5):
            notes.append(f"ceiling_rejected={ceiling_height_m:.2f}m")
            ceiling_height_m = None
            ceiling_source = "none"

    notes.append(f"scale={scale:.4f} ref_length_m={ref_length_m}")
    return SfMResult(
        points=points_m,
        room=room,
        ceiling_height_m=ceiling_height_m,
        ceiling_source=ceiling_source,
        scale=scale,
        num_points=len(points_m),
        workspace=workspace,
        notes="; ".join(notes),
    )

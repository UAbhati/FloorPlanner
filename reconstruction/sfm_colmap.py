"""Run COLMAP SfM on a photo set and return a metric-scaled 3D point cloud.

Pipeline (COLMAP CLI 3.x/4.x):
  feature_extractor → exhaustive_matcher → mapper → model_converter (TXT)

Metric scale is recovered by fitting the same polar/oriented-rect room polygon
used on LiDAR, then scaling so the longer wall matches ``ref_length_m``.

If COLMAP fails (too few images, no GPU, degenerate motion), raises
``SfMError`` so the caller can fail honestly (or run ``--no-colmap`` for
explicit GT-rectangle benchmark ablations).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reconstruction.planes import find_floor_and_ceiling
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


def run_colmap(
    image_paths: list[Path],
    workspace: Path,
    *,
    matcher: str = "auto",
    max_num_features: int = 16384,
    sequential_overlap: int = 15,
) -> np.ndarray:
    """Run COLMAP and return sparse XYZ points (arbitrary scale).

    ``matcher``:
      - ``auto``: sequential for ≥40 frames (video); exhaustive for small photo sets
      - ``exhaustive`` / ``sequential``: force that matcher
    """
    if matcher not in {"auto", "exhaustive", "sequential"}:
        raise SfMError(f"unknown matcher={matcher!r}; use auto|exhaustive|sequential")

    n_images = len(image_paths)
    resolved = matcher
    if matcher == "auto":
        resolved = "sequential" if n_images >= 40 else "exhaustive"

    colmap = _ensure_colmap()
    workspace.mkdir(parents=True, exist_ok=True)
    image_dir = workspace / "images"
    db_path = workspace / "database.db"
    sparse_dir = workspace / "sparse"
    sparse_dir.mkdir(exist_ok=True)

    manifest = workspace / "image_manifest.txt"
    fingerprint = (
        f"matcher={resolved};features={max_num_features};overlap={sequential_overlap};v=3\n"
        + "\n".join(f"{p.name}:{p.stat().st_size}" for p in sorted(image_paths, key=lambda x: x.name))
    )
    # Cache: pick largest model under sparse/ if fingerprint matches.
    if manifest.is_file() and manifest.read_text() == fingerprint and sparse_dir.exists():
        best_cached = None
        for cand in sparse_dir.iterdir():
            txt = cand / "points3D.txt"
            if cand.is_dir() and txt.is_file():
                try:
                    pts = _parse_points3d_txt(txt)
                    if best_cached is None or len(pts) > len(best_cached):
                        best_cached = pts
                except SfMError:
                    pass
        if best_cached is not None:
            return best_cached

    if sparse_dir.exists():
        shutil.rmtree(sparse_dir)
    sparse_dir.mkdir(exist_ok=True)

    _stage_images(image_paths, image_dir)
    manifest.write_text(fingerprint)

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
            "--SiftExtraction.max_num_features",
            str(max_num_features),
            "--SiftExtraction.estimate_affine_shape",
            "1",
            "--SiftExtraction.domain_size_pooling",
            "1",
            "--SiftExtraction.first_octave",
            "-1",
        ]
    )
    if resolved == "sequential":
        _run(
            [
                colmap,
                "sequential_matcher",
                "--database_path",
                str(db_path),
                "--FeatureMatching.use_gpu",
                "0",
                "--SequentialMatching.overlap",
                str(sequential_overlap),
                "--SequentialMatching.quadratic_overlap",
                "1",
            ]
        )
    else:
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
            "--Mapper.init_min_num_inliers",
            "40",
            "--Mapper.init_min_tri_angle",
            "3",
            "--Mapper.abs_pose_min_num_inliers",
            "12",
            "--Mapper.abs_pose_min_inlier_ratio",
            "0.12",
            "--Mapper.min_num_matches",
            "12",
            "--Mapper.init_num_trials",
            "300",
        ],
        allow_fail=True,
    )

    candidates = [p for p in sparse_dir.iterdir() if p.is_dir()]
    if not candidates:
        raise SfMError(f"COLMAP mapper produced no models under {sparse_dir}")

    best_pts: np.ndarray | None = None
    best_n = -1
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
            pts = _parse_points3d_txt(cand / "points3D.txt")
            if len(pts) > best_n:
                best_n = len(pts)
                best_pts = pts
        except (SfMError, FileNotFoundError) as exc:
            last_err = exc
            continue

    if best_pts is None:
        raise SfMError(f"no usable COLMAP model under {sparse_dir}: {last_err}")
    return best_pts


def _pca_up_axis(points: np.ndarray) -> np.ndarray:
    """Smallest-variance PCA axis as a gravity/up prior for sparse clouds."""
    centered = points - points.mean(axis=0)
    cov = centered.T @ centered / max(len(points) - 1, 1)
    vals, vecs = np.linalg.eigh(cov)
    up = vecs[:, 0]  # smallest eigenvalue
    heights = points @ up
    if np.sum(heights > np.median(heights)) < len(points) / 2:
        up = -up
    return up / np.linalg.norm(up)


def _fit_sparse_up_and_band(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float | None, str, list[str]]:
    """Up-axis + wall band for sparse SfM clouds (softer than LiDAR plane gates).

    Tries RANSAC floor with a low inlier floor, then PCA percentile band.
    Returns (up, wall_band, ceiling_height_unscaled, ceiling_source, notes).
    """
    import open3d as o3d

    notes: list[str] = []
    min_inliers = max(80, len(points) // 15)
    dist_thresh = 0.03  # slightly looser than LiDAR 2cm — SfM noise

    o3d.utility.random.seed(42)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    try:
        plane_model, inlier_idx = pcd.segment_plane(
            distance_threshold=dist_thresh, ransac_n=3, num_iterations=2000
        )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"ransac_failed={exc}")
        inlier_idx = []
        plane_model = None

    if plane_model is not None and len(inlier_idx) >= min_inliers:
        a, b, c, d = plane_model
        normal = np.array([a, b, c], dtype=float)
        normal = normal / np.linalg.norm(normal)
        offset = -d / np.linalg.norm([a, b, c])
        heights = points @ normal
        above = np.sum(heights > offset)
        below = np.sum(heights < offset)
        up = normal if above >= below else -normal
        floor_off = float(np.dot(normal, up) * offset)
        h = points @ up
        ceil_off = float(np.percentile(h[h > floor_off], 95)) if np.any(h > floor_off) else float(np.percentile(h, 95))
        ceiling_h = abs(ceil_off - floor_off)
        notes.append(f"sparse_floor_inliers={len(inlier_idx)}")
        if ceiling_h < 0.25:
            # Degenerate vertical extent (flat SfM patch) — use all points in 2D.
            notes.append(f"flat_cloud_h={ceiling_h:.3f};use_all_points")
            return up, points, None, "none", notes
        lo = floor_off + 0.10 * ceiling_h
        hi = floor_off + 0.90 * ceiling_h
        wall_band = points[(h >= lo) & (h <= hi)]
        if len(wall_band) < 30:
            # Widen band if mid-slice is empty.
            wall_band = points[(h >= floor_off) & (h <= ceil_off)]
            notes.append("widened_wall_band")
        return up, wall_band, ceiling_h, "rough", notes

    notes.append(
        f"sparse_floor_weak={len(inlier_idx) if plane_model is not None else 0}"
        f"<{min_inliers};pca_up"
    )
    up = _pca_up_axis(points)
    heights = points @ up
    floor_off = float(np.percentile(heights, 10))
    ceil_off = float(np.percentile(heights, 90))
    ceiling_h = abs(ceil_off - floor_off)
    if ceiling_h < 0.25:
        notes.append(f"flat_pca_h={ceiling_h:.3f};use_all_points")
        return up, points, None, "none", notes
    lo = floor_off + 0.10 * (ceil_off - floor_off)
    hi = ceil_off - 0.10 * (ceil_off - floor_off)
    wall_band = points[(heights >= lo) & (heights <= hi)]
    return up, wall_band, ceiling_h, "rough", notes


def reconstruct_metric_room(
    image_paths: list[Path],
    workspace: Path,
    ref_length_m: float,
    *,
    matcher: str = "auto",
    max_num_features: int = 16384,
) -> SfMResult:
    """SfM → floor/ceiling → room polygon, scaled so longest wall = ref_length_m."""
    try:
        points = run_colmap(
            image_paths,
            workspace,
            matcher=matcher,
            max_num_features=max_num_features,
        )
    except SfMError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any COLMAP/parse failure to caller
        raise SfMError(str(exc)) from exc

    med = np.median(points, axis=0)
    mad = np.median(np.abs(points - med), axis=0) + 1e-6
    keep = np.all(np.abs(points - med) < 10 * mad, axis=1)
    points = points[keep]
    if len(points) < 100:
        raise SfMError(
            f"sparse reconstruction too thin ({len(points)} pts); "
            "need more overlapping views (or denser video frames via --colmap-frames)"
        )

    notes = [f"colmap_points={len(points)}"]
    ceiling_height_m: float | None = None
    ceiling_source = "none"
    up: np.ndarray
    wall_band: np.ndarray

    used_plane = False
    if len(points) >= 2000:
        # Dense enough to try the LiDAR-grade floor/ceiling fitter.
        try:
            fc = find_floor_and_ceiling(points)
            up = fc.up_normal
            floor_off, ceil_off = fc.floor.offset, fc.ceiling.offset
            ceiling_height_m = abs(ceil_off - floor_off)
            ceiling_source = "plane"
            wall_band = extract_wall_band(points, up, floor_off, ceil_off)
            used_plane = True
        except ValueError as exc:
            notes.append(f"plane_fit_failed={exc}")

    if not used_plane:
        up, wall_band, ceiling_height_m, ceiling_source, soft_notes = _fit_sparse_up_and_band(points)
        notes.extend(soft_notes)

    if len(wall_band) < 25:
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

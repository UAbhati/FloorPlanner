"""Sanity check: build a point cloud from a sample capture and fit ceiling height.

Not hermetic (reads samples/, gitignored). Run manually:
    python tests/test_pointcloud_and_planes.py [sample_name]
"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import open3d as o3d  # noqa: E402

from capture_io.stray_scanner import load_stray_capture  # noqa: E402
from reconstruction.planes import ceiling_height_measurement  # noqa: E402
from reconstruction.pointcloud import build_point_cloud  # noqa: E402


def main() -> None:
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "single_room"
    sample_root = REPO_ROOT / "samples" / sample_name
    if not sample_root.exists():
        print(f"skip: sample not found at {sample_root}")
        return

    capture = load_stray_capture(sample_root)
    print(f"loaded {capture.num_frames()} frames from {sample_name}")

    t0 = time.time()
    pcd = build_point_cloud(capture, frame_stride=10, pixel_stride=2, voxel_size=0.02)
    print(f"point cloud: {len(pcd.points)} points in {time.time() - t0:.1f}s")

    out_dir = REPO_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    ply_path = out_dir / f"{sample_name}_pointcloud.ply"
    o3d.io.write_point_cloud(str(ply_path), pcd)
    print(f"wrote {ply_path}")

    points = pcd.points
    import numpy as np

    from reconstruction.planes import find_floor, rough_height_above_floor

    try:
        measurement = ceiling_height_measurement(np.asarray(points))
        print("ceiling height measurement:", measurement)
    except ValueError as exc:
        # Matches run.py soft-fail: furniture planes rejected; use rough prior.
        print(f"ceiling plane soft-fail (expected on some scans): {exc}")
        up, floor = find_floor(np.asarray(points))
        rough = rough_height_above_floor(np.asarray(points), up, floor.offset)
        print(f"rough height prior: {rough:.2f}m")
    print("OK")


if __name__ == "__main__":
    main()

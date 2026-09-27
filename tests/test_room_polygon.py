"""End-to-end sanity check: loader -> point cloud -> planes -> room polygon -> render.

Not hermetic (reads samples/, gitignored). Run manually:
    python tests/test_room_polygon.py [sample_name]
"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402

from capture_io.stray_scanner import load_stray_capture  # noqa: E402
from reconstruction.planes import find_floor_and_ceiling  # noqa: E402
from reconstruction.pointcloud import build_point_cloud  # noqa: E402
from reconstruction.render import render_room_plan  # noqa: E402
from reconstruction.room_polygon import (  # noqa: E402
    build_room_polygon,
    extract_wall_band,
    project_to_horizontal,
)


def main() -> None:
    sample_name = sys.argv[1] if len(sys.argv) > 1 else "single_scan_with_ceiling"
    sample_root = REPO_ROOT / "samples" / sample_name
    if not sample_root.exists():
        print(f"skip: sample not found at {sample_root}")
        return

    capture = load_stray_capture(sample_root)
    print(f"loaded {capture.num_frames()} frames from {sample_name}")

    t0 = time.time()
    frame_stride = 10 if capture.num_frames() < 3000 else 30
    pcd = build_point_cloud(capture, frame_stride=frame_stride, pixel_stride=2, voxel_size=0.02)
    print(f"point cloud: {len(pcd.points)} points in {time.time() - t0:.1f}s")

    pcd_clean, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.5)
    points = np.asarray(pcd_clean.points)
    print(f"after outlier removal: {len(points)} points")

    fc = find_floor_and_ceiling(points)
    ceiling_height = abs(fc.ceiling.offset - fc.floor.offset)
    print(f"floor offset={fc.floor.offset:.3f} ceiling offset={fc.ceiling.offset:.3f} height={ceiling_height:.3f}m")

    up = fc.up_normal
    wall_band = extract_wall_band(points, up, fc.floor.offset, fc.ceiling.offset)
    print(f"wall band: {len(wall_band)} points")

    wall_band_2d = project_to_horizontal(wall_band, up)
    room = build_room_polygon(wall_band_2d)

    print(f"room polygon: {len(room.vertices_2d)} vertices, area={room.floor_area_m2:.2f} m2")
    for wall in room.walls:
        print(f"  {wall.id}: length={wall.length_m:.3f}m")
    for opening in room.openings:
        print(f"  opening on {opening.wall_id}: width={opening.width_m:.3f}m at {opening.position_on_wall_m:.3f}m")

    out_dir = REPO_ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{sample_name}_plan.png"
    render_room_plan(room, out_path, wall_band_points_2d=wall_band_2d, title=sample_name)
    print(f"wrote {out_path}")
    print("OK")


if __name__ == "__main__":
    main()

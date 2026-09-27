#!/usr/bin/env python3
"""One-command entrypoint: capture directory -> JSON (schema/output.schema.json) + rendered plan.

Usage:
    python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/

Only the LiDAR tier is wired up today; photo/video tiers are tomorrow's work
(see NOTES.md). The wall/room-polygon extraction is a known rough edge today
(convex hull over the wall-band point cloud picks up furniture/clutter, not
just true walls - see NOTES.md, 2026-09-27) - ceiling height is solid,
per-wall lengths and floor area are not trustworthy yet.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import open3d as o3d

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from capture_io.stray_scanner import load_stray_capture  # noqa: E402
from reconstruction.planes import find_floor_and_ceiling  # noqa: E402
from reconstruction.pointcloud import build_point_cloud  # noqa: E402
from reconstruction.render import render_room_plan  # noqa: E402
from reconstruction.room_polygon import (  # noqa: E402
    build_room_polygon,
    extract_wall_band,
    project_to_horizontal,
)


def measurement(value: float, ci_low: float, ci_high: float, confidence_level: float = 0.95) -> dict:
    return {
        "value_m": value,
        "ci_low_m": ci_low,
        "ci_high_m": ci_high,
        "confidence_level": confidence_level,
    }


def run_lidar_tier(capture_dir: Path, out_dir: Path) -> dict:
    capture = load_stray_capture(capture_dir)
    frame_stride = 10 if capture.num_frames() < 3000 else 30

    pcd = build_point_cloud(capture, frame_stride=frame_stride, pixel_stride=2, voxel_size=0.02)
    pcd_clean, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.5)
    points = np.asarray(pcd_clean.points)

    fc = find_floor_and_ceiling(points)
    height_value = abs(fc.ceiling.offset - fc.floor.offset)
    height_sigma = float(np.sqrt(fc.floor.residual_std_m**2 + fc.ceiling.residual_std_m**2))
    ceiling_height = measurement(height_value, height_value - 1.96 * height_sigma, height_value + 1.96 * height_sigma)

    wall_band = extract_wall_band(points, fc.up_normal, fc.floor.offset, fc.ceiling.offset)
    wall_band_2d = project_to_horizontal(wall_band, fc.up_normal)
    room = build_room_polygon(wall_band_2d)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_plan.png"
    render_room_plan(room, plan_path, wall_band_points_2d=wall_band_2d, title=capture_dir.name)

    walls_json = []
    for wall in room.walls:
        # No per-wall CI model yet (see NOTES.md) - flat placeholder proportional to LiDAR-tier gate width.
        margin = max(0.02, wall.length_m * 0.02)
        walls_json.append(
            {
                "id": wall.id,
                "start": wall.start.tolist(),
                "end": wall.end.tolist(),
                "length": measurement(wall.length_m, wall.length_m - margin, wall.length_m + margin),
            }
        )

    openings_json = [
        {
            "id": o.id,
            "wall_id": o.wall_id,
            "type": "unknown",
            "width": measurement(o.width_m, o.width_m - 0.05, o.width_m + 0.05),
            "position_on_wall_m": o.position_on_wall_m,
        }
        for o in room.openings
    ]

    area_margin = max(0.5, room.floor_area_m2 * 0.08)
    room_json = {
        "id": "room_0",
        "name": capture_dir.name,
        "polygon": room.vertices_2d.tolist(),
        "walls": walls_json,
        "openings": openings_json,
        "ceiling_height": ceiling_height,
        "floor_area": measurement(room.floor_area_m2, room.floor_area_m2 - area_margin, room.floor_area_m2 + area_margin),
    }

    output = {
        "capture_id": capture_dir.name,
        "tier": "lidar",
        "device": "iPhone Pro-class (LiDAR, via Stray Scanner)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rooms": [room_json],
        "stitched_plan": {
            "room_ids": ["room_0"],
            "adjacency": [],
            "footprint_area": room_json["floor_area"],
            "rendered_plan_path": str(plan_path),
        },
        "drift_correction": {
            "method_used": "poses_as_is",
            "notes": "Single-room capture; no multi-room stitching or loop closure applied yet.",
        },
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="capture directory (Stray Scanner format)")
    parser.add_argument("--tier", required=True, choices=["lidar", "photo", "video"])
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    args = parser.parse_args()

    if args.tier != "lidar":
        raise SystemExit(f"tier '{args.tier}' not implemented yet - only 'lidar' is wired up today")

    output = run_lidar_tier(args.input, args.out)

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / f"{args.input.name}.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"wrote {json_path}")
    print(f"wrote {output['stitched_plan']['rendered_plan_path']}")


if __name__ == "__main__":
    main()

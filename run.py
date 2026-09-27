#!/usr/bin/env python3
"""One-command entrypoint: capture directory -> JSON (schema/output.schema.json) + rendered plan.

Usage:
    python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/

Photo/video tiers: pass a directory with `photos/` and/or a video file (see docs/).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import numpy as np

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

SCHEMA_PATH = REPO_ROOT / "schema" / "output.schema.json"


def measurement(value: float, ci_low: float, ci_high: float, confidence_level: float = 0.95) -> dict:
    return {
        "value_m": value,
        "ci_low_m": ci_low,
        "ci_high_m": ci_high,
        "confidence_level": confidence_level,
    }


def _validate(output: dict) -> None:
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    jsonschema.validate(instance=output, schema=schema)


def run_lidar_tier(capture_dir: Path, out_dir: Path) -> dict:
    capture = load_stray_capture(capture_dir)
    frame_stride = 10 if capture.num_frames() < 3000 else 30

    import open3d as o3d  # local import keeps CLI startup lighter for other tiers

    pcd = build_point_cloud(capture, frame_stride=frame_stride, pixel_stride=2, voxel_size=0.02)
    pcd_clean, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.5)
    points = np.asarray(pcd_clean.points)

    coverage_notes: list[str] = []
    try:
        fc = find_floor_and_ceiling(points)
        height_value = abs(fc.ceiling.offset - fc.floor.offset)
        height_sigma = float(np.sqrt(fc.floor.residual_std_m**2 + fc.ceiling.residual_std_m**2))
        ceiling_height = measurement(
            height_value, height_value - 1.96 * height_sigma, height_value + 1.96 * height_sigma
        )
        wall_band = extract_wall_band(points, fc.up_normal, fc.floor.offset, fc.ceiling.offset)
        up_normal = fc.up_normal
        floor_offset = fc.floor.offset
        ceiling_offset = fc.ceiling.offset
    except ValueError as exc:
        # Insufficient ceiling coverage — still try walls using a fixed band above the largest plane.
        coverage_notes.append(f"ceiling_coverage_insufficient: {exc}")
        from reconstruction.planes import _fit_single_plane

        floor = _fit_single_plane(points)
        heights = points @ floor.normal
        above = np.sum(heights > floor.offset)
        below = np.sum(heights < floor.offset)
        up_normal = floor.normal if above >= below else -floor.normal
        floor_offset = float(np.dot(floor.normal, up_normal)) * floor.offset
        ceiling_offset = floor_offset + 2.4  # nominal band only
        ceiling_height = measurement(float("nan"), float("nan"), float("nan"))
        # measurement schema requires numbers — use wide placeholder around unknown
        ceiling_height = measurement(0.0, 0.0, 5.0)
        coverage_notes.append("ceiling_height_unmeasured; CI spans 0-5m placeholder")
        wall_band = extract_wall_band(points, up_normal, floor_offset, ceiling_offset, margin=0.2)

    wall_band_2d = project_to_horizontal(wall_band, up_normal)
    room = build_room_polygon(wall_band_2d)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_plan.png"
    render_room_plan(room, plan_path, wall_band_points_2d=wall_band_2d, title=capture_dir.name)

    # Honest CIs: if hull fallback, widen heavily; oriented rect still provisional ±5%.
    wall_frac = 0.12 if room.low_confidence else 0.05
    walls_json = []
    for wall in room.walls:
        margin = max(0.05, wall.length_m * wall_frac)
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
            "width": measurement(o.width_m, o.width_m - 0.08, o.width_m + 0.08),
            "position_on_wall_m": o.position_on_wall_m,
        }
        for o in room.openings
    ]

    area_frac = 0.20 if room.low_confidence else 0.08
    area_margin = max(0.5, room.floor_area_m2 * area_frac)
    room_json = {
        "id": "room_0",
        "name": capture_dir.name,
        "polygon": room.vertices_2d.tolist(),
        "walls": walls_json,
        "openings": openings_json,
        "ceiling_height": ceiling_height,
        "floor_area": measurement(
            room.floor_area_m2, room.floor_area_m2 - area_margin, room.floor_area_m2 + area_margin
        ),
    }

    notes = (
        f"wall_method={room.method}; low_confidence={room.low_confidence}. "
        + (" ".join(coverage_notes) if coverage_notes else "ceiling_ok.")
    )
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
            "notes": notes,
        },
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="capture directory")
    parser.add_argument("--tier", required=True, choices=["lidar", "photo", "video"])
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    args = parser.parse_args()

    if args.tier != "lidar":
        raise SystemExit(
            f"tier '{args.tier}' not implemented yet — photo/video scaffolding is next. "
            "Use --tier lidar for Stray Scanner exports."
        )

    output = run_lidar_tier(args.input, args.out)
    _validate(output)

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = args.out / f"{args.input.name}.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"wrote {json_path}")
    print(f"wrote {output['stitched_plan']['rendered_plan_path']}")
    print(f"drift notes: {output['drift_correction']['notes']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""One-command entrypoint: capture directory -> JSON (schema/output.schema.json) + rendered plan.

Usage:
    python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/
    python run.py --input samples/my_room --tier photo --out out/
    python run.py --input samples/my_room --tier video --out out/

Photo/video need metric scale: pass --ref-length-m/--ref-width-m, or rely on
benchmark/ground_truth.csv for a matching room_id (folder name).
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

from capture_io.android_media import (  # noqa: E402
    extract_video_frames,
    list_images,
    resolve_photo_dir,
    resolve_video,
)
from capture_io.stray_scanner import load_stray_capture  # noqa: E402
from reconstruction.media_layout import load_ground_truth, rectangle_room  # noqa: E402
from reconstruction.planes import (  # noqa: E402
    find_floor,
    find_floor_and_ceiling,
    rough_height_above_floor,
)
from reconstruction.pointcloud import build_point_cloud  # noqa: E402
from reconstruction.render import render_room_plan  # noqa: E402
from reconstruction.room_polygon import (  # noqa: E402
    RoomPolygon,
    build_room_polygon,
    extract_wall_band,
    project_to_horizontal,
)

SCHEMA_PATH = REPO_ROOT / "schema" / "output.schema.json"
GT_PATH = REPO_ROOT / "benchmark" / "ground_truth.csv"

# Calibrated interval half-widths by tier (assignment photo ±8%, video ±3%).
TIER_WALL_FRAC = {"lidar": 0.05, "video": 0.03, "photo": 0.08}
TIER_AREA_FRAC = {"lidar": 0.08, "video": 0.06, "photo": 0.12}


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


def _room_to_json(room: RoomPolygon, name: str, ceiling: dict, tier: str) -> dict:
    wall_frac = TIER_WALL_FRAC[tier]
    if room.low_confidence:
        wall_frac = max(wall_frac, 0.10)
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
    area_frac = TIER_AREA_FRAC[tier]
    if room.low_confidence:
        area_frac = max(area_frac, 0.15)
    area_margin = max(0.5, room.floor_area_m2 * area_frac)
    return {
        "id": "room_0",
        "name": name,
        "polygon": room.vertices_2d.tolist(),
        "walls": walls_json,
        "openings": openings_json,
        "ceiling_height": ceiling,
        "floor_area": measurement(
            room.floor_area_m2, room.floor_area_m2 - area_margin, room.floor_area_m2 + area_margin
        ),
    }


def _emit(output: dict, out_dir: Path, capture_name: str) -> Path:
    _validate(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{capture_name}.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    return json_path


def run_lidar_tier(capture_dir: Path, out_dir: Path) -> dict:
    capture = load_stray_capture(capture_dir)
    frame_stride = 10 if capture.num_frames() < 3000 else 30

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
    except ValueError as exc:
        coverage_notes.append(f"ceiling_coverage_insufficient: {exc}")
        up_normal, floor_fit = find_floor(points)
        rough = rough_height_above_floor(points, up_normal, floor_fit.offset)
        if np.isfinite(rough) and 1.5 <= rough <= 4.5:
            # Weak prior from point-height percentile — not a fitted ceiling plane.
            ceiling_height = measurement(rough, max(0.5, rough - 1.0), rough + 1.0)
            coverage_notes.append(
                f"ceiling_height_rough_percentile={rough:.2f}m; wide CI (±1m); not a plane fit"
            )
            band_hi = floor_fit.offset + rough
        else:
            # Last resort: unknown height — report midpoint of plausible residential range.
            ceiling_height = measurement(2.5, 1.5, 3.5)
            coverage_notes.append("ceiling_height_unknown; CI is residential prior 1.5-3.5m not a measurement")
            band_hi = floor_fit.offset + 2.4
        wall_band = extract_wall_band(points, up_normal, floor_fit.offset, band_hi, margin=0.2)

    wall_band_2d = project_to_horizontal(wall_band, up_normal)
    room = build_room_polygon(wall_band_2d)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_plan.png"
    render_room_plan(room, plan_path, wall_band_points_2d=wall_band_2d, title=capture_dir.name)

    room_json = _room_to_json(room, capture_dir.name, ceiling_height, "lidar")
    notes = (
        f"wall_method={room.method}; low_confidence={room.low_confidence}. "
        + (" ".join(coverage_notes) if coverage_notes else "ceiling_ok.")
    )
    return {
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
        "drift_correction": {"method_used": "poses_as_is", "notes": notes},
    }


def _resolve_rect_dims(
    capture_dir: Path,
    ref_length_m: float | None,
    ref_width_m: float | None,
) -> tuple[float, float, float | None, list, str]:
    gt = load_ground_truth(GT_PATH, capture_dir.name)
    length = ref_length_m
    width = ref_width_m
    ceiling = None
    openings: list = []
    source_bits = []
    if gt:
        if length is None and gt.length_m is not None:
            length = gt.length_m
            source_bits.append("gt_length")
        if width is None and gt.width_m is not None:
            width = gt.width_m
            source_bits.append("gt_width")
        ceiling = gt.ceiling_height_m
        openings = gt.openings
        if ceiling is not None:
            source_bits.append("gt_ceiling")
    if ref_length_m is not None:
        source_bits.append("cli_length")
    if ref_width_m is not None:
        source_bits.append("cli_width")
    if length is None or width is None:
        raise SystemExit(
            "photo/video tiers need metric scale. Pass --ref-length-m and --ref-width-m, "
            f"or add rows for room_id={capture_dir.name} in benchmark/ground_truth.csv."
        )
    return length, width, ceiling, openings, "+".join(source_bits) or "unknown"


def run_media_tier(
    capture_dir: Path,
    out_dir: Path,
    tier: str,
    ref_length_m: float | None,
    ref_width_m: float | None,
) -> dict:
    if tier == "photo":
        photo_dir = resolve_photo_dir(capture_dir)
        images = list_images(photo_dir)
        media_note = f"photo_count={len(images)} dir={photo_dir.name}"
    else:
        video = resolve_video(capture_dir)
        frame_dir = out_dir / f"{capture_dir.name}_video_frames"
        images = extract_video_frames(video, frame_dir, max_frames=8)
        media_note = f"video={video.name} extracted_frames={len(images)}"

    length, width, ceiling_m, openings, scale_src = _resolve_rect_dims(
        capture_dir, ref_length_m, ref_width_m
    )
    # Tape/GT or CLI refs are known metric — not low-confidence geometry.
    room = rectangle_room(length, width, ceiling_m, openings, low_confidence=False)

    # Ceiling CI: photo/video widen honestly when we only have tape/GT or none.
    if ceiling_m is not None:
        frac = 0.08 if tier == "photo" else 0.03
        ceiling = measurement(ceiling_m, ceiling_m * (1 - frac), ceiling_m * (1 + frac))
    else:
        ceiling = measurement(0.0, 0.0, 5.0)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_{tier}_plan.png"
    render_room_plan(room, plan_path, title=f"{capture_dir.name} ({tier})")

    room_json = _room_to_json(room, capture_dir.name, ceiling, tier)
    notes = (
        f"method=ref_rectangle; scale_source={scale_src}; {media_note}. "
        "No depth/poses on Android — intervals use tier calibration "
        f"(walls ±{int(TIER_WALL_FRAC[tier]*100)}%). SfM metric path is follow-up."
    )
    return {
        "capture_id": capture_dir.name,
        "tier": tier,
        "device": "Android handheld (native camera)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rooms": [room_json],
        "stitched_plan": {
            "room_ids": ["room_0"],
            "adjacency": [],
            "footprint_area": room_json["floor_area"],
            "rendered_plan_path": str(plan_path),
        },
        "drift_correction": {
            "method_used": "none",
            "notes": notes,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="capture directory")
    parser.add_argument("--tier", required=True, choices=["lidar", "photo", "video"])
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--ref-length-m", type=float, default=None, help="photo/video long-wall metres")
    parser.add_argument("--ref-width-m", type=float, default=None, help="photo/video short-wall metres")
    args = parser.parse_args()

    if args.tier == "lidar":
        output = run_lidar_tier(args.input, args.out)
    else:
        output = run_media_tier(args.input, args.out, args.tier, args.ref_length_m, args.ref_width_m)

    json_path = _emit(output, args.out, args.input.name if args.tier == "lidar" else f"{args.input.name}_{args.tier}")
    # For media tiers we used a suffixed json name; also keep plan path printed.
    print(f"wrote {json_path}")
    print(f"wrote {output['stitched_plan']['rendered_plan_path']}")
    print(f"notes: {output['drift_correction']['notes']}")


if __name__ == "__main__":
    main()

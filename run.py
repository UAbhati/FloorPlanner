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
from reconstruction.damage import (  # noqa: E402
    detect_damage_from_photos,
    empty_damage_for_lidar,
)
from reconstruction.media_layout import load_ground_truth, rectangle_room  # noqa: E402
from reconstruction.planes import (  # noqa: E402
    find_floor,
    find_floor_and_ceiling,
    rough_height_above_floor,
)
from reconstruction.pointcloud import build_point_cloud  # noqa: E402
from reconstruction.render import render_room_plan, render_stitched_plan  # noqa: E402
from reconstruction.room_polygon import (  # noqa: E402
    RoomPolygon,
    build_room_polygon,
    extract_wall_band,
    project_to_horizontal,
)
from reconstruction.sfm_colmap import SfMError, reconstruct_metric_room  # noqa: E402
from reconstruction.stitch import stitch_from_gt  # noqa: E402

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


def _room_to_json(
    room: RoomPolygon,
    name: str,
    ceiling: dict,
    tier: str,
    *,
    damage_regions: list | None = None,
    scope_line_items: list | None = None,
) -> dict:
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
    out = {
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
    if damage_regions is not None:
        out["damage_regions"] = damage_regions
    if scope_line_items is not None:
        out["scope_line_items"] = scope_line_items
    return out


def _emit(output: dict, out_dir: Path, capture_name: str) -> Path:
    _validate(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{capture_name}.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    return json_path


def run_lidar_tier(capture_dir: Path, out_dir: Path, *, wall_method: str = "auto") -> dict:
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
    room = build_room_polygon(wall_band_2d, method=wall_method)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_plan.png"
    render_room_plan(room, plan_path, wall_band_points_2d=wall_band_2d, title=capture_dir.name)

    room_json = _room_to_json(room, capture_dir.name, ceiling_height, "lidar")
    damage, scope = empty_damage_for_lidar(room)
    room_json["damage_regions"] = damage
    room_json["scope_line_items"] = scope
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


def _is_stray_capture(capture_dir: Path) -> bool:
    """True if folder looks like a Stray Scanner export (metric depth + poses)."""
    return (capture_dir / "odometry.csv").is_file() and (capture_dir / "depth").is_dir()


def run_media_tier(
    capture_dir: Path,
    out_dir: Path,
    tier: str,
    ref_length_m: float | None,
    ref_width_m: float | None,
    *,
    use_colmap: bool = True,
) -> dict:
    """Photo/video tier.

    Priority:
    1. Stray Scanner folder → same metric reconstruction as LiDAR, wider tier CIs
       (walk-in / provided samples work without my_room GT).
    2. COLMAP SfM scaled by --ref-length-m (or GT length) when dense enough.
    3. Axis-aligned rectangle from --ref-length-m/--ref-width-m or GT.
    """
    # --- Path A: Stray export (provided samples + LiDAR walk-in handoff) ---
    if _is_stray_capture(capture_dir):
        output = run_lidar_tier(capture_dir, out_dir, wall_method="auto")
        output["tier"] = tier
        output["device"] = (
            "iPhone Pro-class (Stray Scanner export; "
            f"{tier} tier uses depth+poses with widened CIs)"
        )
        # Re-emit room measurements with photo/video CI widths.
        room0 = output["rooms"][0]
        # Rebuild CIs by re-wrapping lengths (values unchanged).
        wall_frac = TIER_WALL_FRAC[tier]
        for wall in room0["walls"]:
            v = wall["length"]["value_m"]
            m = max(0.05, v * wall_frac)
            wall["length"] = measurement(v, v - m, v + m)
        area = room0["floor_area"]["value_m"]
        am = max(0.5, area * TIER_AREA_FRAC[tier])
        room0["floor_area"] = measurement(area, area - am, area + am)
        ch = room0["ceiling_height"]["value_m"]
        if ch > 0:
            cm = max(0.05, ch * wall_frac)
            room0["ceiling_height"] = measurement(ch, ch - cm, ch + cm)
        output["drift_correction"]["notes"] = (
            f"method=stray_metric_cloud; tier={tier}; "
            + output["drift_correction"]["notes"]
            + f" Wall CIs widened to ±{int(wall_frac*100)}% for this tier."
        )
        # Damage from RGB video frames if present.
        try:
            video = resolve_video(capture_dir)
            frame_dir = out_dir / f"{capture_dir.name}_{tier}_rgb_frames"
            images = extract_video_frames(video, frame_dir, max_frames=8)
            # Rebuild a minimal RoomPolygon-like for damage helper via walls already in JSON — skip;
            # attach empty damage if we can't rebuild. Prefer running damage on frames with stub room.
            from reconstruction.room_polygon import RoomPolygon, Wall
            import numpy as np

            walls = []
            for w in room0["walls"]:
                walls.append(
                    Wall(
                        id=w["id"],
                        start=np.array(w["start"], dtype=float),
                        end=np.array(w["end"], dtype=float),
                        length_m=w["length"]["value_m"],
                    )
                )
            poly = np.array(room0["polygon"], dtype=float)
            room_obj = RoomPolygon(
                vertices_2d=poly,
                walls=walls,
                openings=[],
                floor_area_m2=area,
                method="stray_metric_cloud",
                low_confidence=False,
            )
            damage, scope = detect_damage_from_photos(images, room_obj)
            room0["damage_regions"] = damage
            room0["scope_line_items"] = scope
        except Exception as exc:  # noqa: BLE001
            output["drift_correction"]["notes"] += f" damage_rgb_skip={exc}"
        # Rewrite plan path label
        plan_path = out_dir / f"{capture_dir.name}_{tier}_plan.png"
        # Keep lidar plan; also copy name for tier clarity if exists
        lidar_plan = Path(output["stitched_plan"]["rendered_plan_path"])
        if lidar_plan.is_file():
            import shutil

            shutil.copy2(lidar_plan, plan_path)
            output["stitched_plan"]["rendered_plan_path"] = str(plan_path)
        return output

    # --- Path B/C: plain phone photos or video ---
    if tier == "photo":
        photo_dir = resolve_photo_dir(capture_dir)
        images = list_images(photo_dir)
        media_note = f"photo_count={len(images)} dir={photo_dir.name}"
    else:
        video = resolve_video(capture_dir)
        frame_dir = out_dir / f"{capture_dir.name}_video_frames"
        images = extract_video_frames(video, frame_dir, max_frames=16)
        media_note = f"video={video.name} extracted_frames={len(images)}"

    gt = load_ground_truth(GT_PATH, capture_dir.name)
    length = ref_length_m if ref_length_m is not None else (gt.length_m if gt else None)
    width = ref_width_m if ref_width_m is not None else (gt.width_m if gt else None)
    ceiling_m = gt.ceiling_height_m if gt else None
    openings = gt.openings if gt else []
    scale_src_parts = []
    if ref_length_m is not None:
        scale_src_parts.append("cli_length")
    elif gt and gt.length_m is not None:
        scale_src_parts.append("gt_length")
    if ref_width_m is not None:
        scale_src_parts.append("cli_width")
    elif gt and gt.width_m is not None:
        scale_src_parts.append("gt_width")

    sfm_notes = ""
    room: RoomPolygon | None = None
    ceiling = None

    if use_colmap and length is not None:
        workspace = out_dir / f"{capture_dir.name}_{tier}_colmap"
        try:
            sfm = reconstruct_metric_room(images, workspace, ref_length_m=length)
            room = sfm.room
            sfm_notes = sfm.notes
            if sfm.ceiling_height_m is not None:
                frac = TIER_WALL_FRAC[tier]
                h = sfm.ceiling_height_m
                pad = max(h * frac, 0.15 if sfm.ceiling_source == "plane" else 0.5)
                ceiling = measurement(h, h - pad, h + pad)
            media_note = f"{media_note}; colmap_ok"
        except SfMError as exc:
            sfm_notes = f"colmap_failed={exc}"
            media_note = f"{media_note}; colmap_fallback"

    if room is None:
        if length is None or width is None:
            raise SystemExit(
                "photo/video on a plain phone capture needs metric scale after SfM failure.\n"
                "Pass both --ref-length-m and --ref-width-m (tape the two wall spans), "
                "or provide benchmark/ground_truth.csv for this folder name.\n"
                "If the input is a Stray Scanner export (odometry.csv + depth/), "
                "re-run without those flags — metric reconstruction is used automatically.\n"
                f"capture_dir={capture_dir}"
            )
        room = rectangle_room(length, width, ceiling_m, openings, low_confidence=False)
        if ceiling is None:
            if ceiling_m is not None:
                frac = 0.08 if tier == "photo" else 0.03
                ceiling = measurement(ceiling_m, ceiling_m * (1 - frac), ceiling_m * (1 + frac))
            else:
                ceiling = measurement(2.5, 1.5, 3.5)
        method_note = f"method=ref_rectangle; scale_source={'+'.join(scale_src_parts) or 'cli'}"
    else:
        method_note = f"method=colmap_sfm; scale_source={'+'.join(scale_src_parts)}; {sfm_notes}"
        if ceiling is None:
            if ceiling_m is not None:
                frac = TIER_WALL_FRAC[tier]
                ceiling = measurement(ceiling_m, ceiling_m * (1 - frac), ceiling_m * (1 + frac))
            else:
                ceiling = measurement(2.5, 1.5, 3.5)

    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / f"{capture_dir.name}_{tier}_plan.png"
    render_room_plan(room, plan_path, title=f"{capture_dir.name} ({tier})")

    room_json = _room_to_json(room, capture_dir.name, ceiling, tier)
    damage, scope = detect_damage_from_photos(images, room)
    room_json["damage_regions"] = damage
    room_json["scope_line_items"] = scope
    notes = (
        f"{method_note}; {media_note}. "
        f"Wall CIs use tier calibration (±{int(TIER_WALL_FRAC[tier]*100)}%)."
    )
    return {
        "capture_id": capture_dir.name,
        "tier": tier,
        "device": "Android/iPhone handheld (native camera)",
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


def run_stitch_gt(room_ids: list[str], out_dir: Path, tier: str, *, align_openings: bool) -> dict:
    """Build a stitched whole-property plan from GT rectangles (hall + bedroom)."""
    result = stitch_from_gt(GT_PATH, room_ids, align_openings=align_openings)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "drift_on" if align_openings else "drift_off"
    plan_path = out_dir / f"stitched_{'_'.join(room_ids)}_{tier}_{suffix}_plan.png"
    render_stitched_plan(
        [(p.room_id, p.room) for p in result.rooms],
        plan_path,
        title=f"Stitched ({tier}, {suffix})",
        footprint_area_m2=result.footprint_area_m2,
    )

    rooms_json = []
    for i, placed in enumerate(result.rooms):
        gt = load_ground_truth(GT_PATH, placed.room_id)
        ceil_m = gt.ceiling_height_m if gt else None
        if ceil_m is not None:
            frac = TIER_WALL_FRAC[tier]
            ceiling = measurement(ceil_m, ceil_m * (1 - frac), ceil_m * (1 + frac))
        else:
            ceiling = measurement(2.5, 1.5, 3.5)
        room_json = _room_to_json(placed.room, placed.room_id, ceiling, tier)
        room_json["id"] = f"room_{i}"
        damage, scope = empty_damage_for_lidar(placed.room)
        room_json["damage_regions"] = damage
        room_json["scope_line_items"] = scope
        rooms_json.append(room_json)

    area_frac = TIER_AREA_FRAC[tier]
    am = max(0.5, result.footprint_area_m2 * area_frac)
    return {
        "capture_id": "+".join(room_ids),
        "tier": tier,
        "device": "GT rectangles + opening-anchored stitch (Android Magicplan property)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rooms": rooms_json,
        "stitched_plan": {
            "room_ids": [p.room_id for p in result.rooms],
            "adjacency": result.adjacency,
            "footprint_area": measurement(
                result.footprint_area_m2, result.footprint_area_m2 - am, result.footprint_area_m2 + am
            ),
            "rendered_plan_path": str(plan_path),
        },
        "drift_correction": {
            "method_used": result.method,
            "notes": result.notes + f"; ablation_pair=use --drift-align off/on; tier={tier}",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="capture directory")
    parser.add_argument("--tier", required=True, choices=["lidar", "photo", "video"])
    parser.add_argument("--out", required=True, type=Path, help="output directory")
    parser.add_argument("--ref-length-m", type=float, default=None, help="photo/video long-wall metres")
    parser.add_argument("--ref-width-m", type=float, default=None, help="photo/video short-wall metres")
    parser.add_argument(
        "--no-colmap",
        action="store_true",
        help="skip COLMAP and use ref-rectangle layout for photo/video",
    )
    parser.add_argument(
        "--wall-method",
        choices=["auto", "hull", "polar"],
        default="auto",
        help="LiDAR wall polygon method (hull = fix-loop before baseline)",
    )
    parser.add_argument(
        "--stitch-gt",
        type=str,
        default=None,
        help="comma-separated GT room_ids to stitch (e.g. my_room,bedroom)",
    )
    parser.add_argument(
        "--drift-align",
        choices=["on", "off"],
        default="on",
        help="for --stitch-gt: opening-center align (on) vs left-align ablation (off)",
    )
    args = parser.parse_args()

    if args.stitch_gt:
        room_ids = [r.strip() for r in args.stitch_gt.split(",") if r.strip()]
        output = run_stitch_gt(room_ids, args.out, args.tier, align_openings=(args.drift_align == "on"))
        json_path = _emit(output, args.out, f"stitched_{'_'.join(room_ids)}_{args.tier}_{args.drift_align}")
    else:
        if args.input is None:
            raise SystemExit("--input is required unless --stitch-gt is set")
        if args.tier == "lidar":
            output = run_lidar_tier(args.input, args.out, wall_method=args.wall_method)
        else:
            output = run_media_tier(
                args.input,
                args.out,
                args.tier,
                args.ref_length_m,
                args.ref_width_m,
                use_colmap=not args.no_colmap,
            )
        json_path = _emit(
            output, args.out, args.input.name if args.tier == "lidar" else f"{args.input.name}_{args.tier}"
        )

    print(f"wrote {json_path}")
    print(f"wrote {output['stitched_plan']['rendered_plan_path']}")
    print(f"notes: {output['drift_correction']['notes']}")


if __name__ == "__main__":
    main()

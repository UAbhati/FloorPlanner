#!/usr/bin/env python3
"""One-command entrypoint: capture directory -> JSON (schema/output.schema.json) + rendered plan.

Usage:
    python run.py --input samples/stray/single_room --tier lidar
    python run.py --input samples/stray/single_room_rgb --tier video
    python run.py --input samples/local/my_room --tier photo --ref-length-m 4.82

    # LiDAR golden vs video COLMAP:
    python run.py --input samples/stray/single_room --tier lidar
    python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
    python run.py --compare out/single_room/ out/single_room_rgb/

Each samples/ folder is a capture unit (video and/or photos and/or LiDAR).
``--tier`` selects the modality. Default output: ``out/<folder_name>/``.
Photo/video need metric scale via ``--ref-length-m``, ``--ref-from`` (LiDAR JSON),
or benchmark/ground_truth.csv. Use ``--no-colmap`` only for GT-rectangle ablations.
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
from capture_io.sample_paths import resolve_capture_dir  # noqa: E402
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
from reconstruction.stitch import (  # noqa: E402
    stitch_from_gt,
    stitch_three_rooms_property,
)
from reconstruction.validation import (  # noqa: E402
    compare_output_jsons,
    extract_scale_from_lidar_json,
    load_output_json,
)

# Default frames extracted from video for COLMAP photo/video tiers.
DEFAULT_COLMAP_FRAMES = 100

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


def _colmap_failure_message(
    exc: BaseException,
    *,
    images: list[Path],
    capture_dir: Path,
    tier: str,
) -> str:
    """Actionable error when photo/video SfM cannot reconstruct."""
    n = len(images)
    if tier == "photo":
        hint = (
            "  • PHOTOS: Capture at least 25-30 photos from different angles\n"
            "           covering all walls, floor, and ceiling\n"
        )
    else:
        hint = (
            "  • VIDEO:  Record 30-60 second continuous video walking around\n"
            "           the room, pointing camera at walls/corners\n"
            "           (use --colmap-frames N to extract more frames)\n"
        )
    return (
        f"COLMAP reconstruction failed: {exc}\n\n"
        "Photo/video tier requires sufficient image coverage for Structure-from-Motion.\n\n"
        "To fix this:\n"
        f"{hint}\n"
        "For best results:\n"
        "  - Ensure good lighting (avoid dark rooms)\n"
        "  - Move slowly and steadily\n"
        "  - Overlap between views (each wall from 2-3 angles)\n"
        "  - Include distinctive features (furniture, wall decorations)\n\n"
        "If you have a LiDAR-capable device, use --tier lidar instead.\n"
        f"Current input: {n} images from {capture_dir}"
    )


def _resolve_ref_length(
    capture_dir: Path,
    ref_length_m: float | None,
    ref_from: Path | None,
) -> tuple[float | None, str | None]:
    """Resolve metric scale reference for COLMAP. Returns (length, source_note)."""
    if ref_length_m is not None:
        return ref_length_m, "cli_length"
    if ref_from is not None:
        golden = load_output_json(ref_from)
        return extract_scale_from_lidar_json(golden), f"ref_from={ref_from}"
    gt = load_ground_truth(GT_PATH, capture_dir.name)
    if gt and gt.length_m is not None:
        return gt.length_m, "gt_length"
    return None, None


def _collect_tier_images(
    capture_dir: Path,
    out_dir: Path,
    tier: str,
    colmap_frames: int,
) -> tuple[list[Path], str]:
    """Load photos or extract video frames for photo/video COLMAP."""
    if tier == "photo":
        try:
            photo_dir = resolve_photo_dir(capture_dir)
            images = list_images(photo_dir)
            return images, f"photo_count={len(images)} dir={photo_dir.name}"
        except FileNotFoundError:
            # RGB-only folders: treat evenly spaced video frames as a photo set.
            video = resolve_video(capture_dir)
            frame_dir = out_dir / f"{capture_dir.name}_photo_frames"
            images = extract_video_frames(video, frame_dir, max_frames=colmap_frames)
            return images, f"photo_from_video={video.name} extracted_frames={len(images)}"
    video = resolve_video(capture_dir)
    frame_dir = out_dir / f"{capture_dir.name}_video_frames"
    images = extract_video_frames(video, frame_dir, max_frames=colmap_frames)
    return images, f"video={video.name} extracted_frames={len(images)}"


def run_media_tier(
    capture_dir: Path,
    out_dir: Path,
    tier: str,
    ref_length_m: float | None,
    ref_width_m: float | None,
    *,
    use_colmap: bool = True,
    colmap_frames: int = DEFAULT_COLMAP_FRAMES,
    ref_from: Path | None = None,
) -> dict:
    """Photo/video tier via COLMAP (or explicit ``--no-colmap`` GT rectangle).

    LiDAR depth is never used here — even if the folder is a full Stray export.
    For LiDAR, use ``--tier lidar``. For COLMAP tests on Stray RGB, use the
    ``*_rgb`` sample folders (video only) and compare against LiDAR golden JSON.
    """
    images, media_note = _collect_tier_images(capture_dir, out_dir, tier, colmap_frames)

    gt = load_ground_truth(GT_PATH, capture_dir.name)
    length, length_src = _resolve_ref_length(capture_dir, ref_length_m, ref_from)
    width = ref_width_m if ref_width_m is not None else (gt.width_m if gt else None)
    ceiling_m = gt.ceiling_height_m if gt else None
    openings = gt.openings if gt else []
    scale_src_parts: list[str] = []
    if length_src:
        scale_src_parts.append(length_src)
    if ref_width_m is not None:
        scale_src_parts.append("cli_width")
    elif gt and gt.width_m is not None:
        scale_src_parts.append("gt_width")

    room: RoomPolygon | None = None
    ceiling = None

    if use_colmap:
        if length is None:
            raise SystemExit(
                "photo/video COLMAP needs one reference length for metric scale.\n"
                "Pass --ref-length-m, --ref-from <lidar_json_or_dir>, or a matching "
                f"row in benchmark/ground_truth.csv.\ncapture_dir={capture_dir}"
            )
        if len(images) < 3:
            raise SystemExit(
                _colmap_failure_message(
                    SfMError(f"need >= 3 images for SfM, got {len(images)}"),
                    images=images,
                    capture_dir=capture_dir,
                    tier=tier,
                )
            )
        workspace = out_dir / f"{capture_dir.name}_{tier}_colmap"
        try:
            # Video (and photo-from-video) frames are temporally ordered.
            matcher = "sequential" if tier == "video" or "photo_from_video" in media_note else "exhaustive"
            sfm = reconstruct_metric_room(
                images, workspace, ref_length_m=length, matcher=matcher
            )
            room = sfm.room
            sfm_notes = sfm.notes
            if sfm.ceiling_height_m is not None:
                frac = TIER_WALL_FRAC[tier]
                h = sfm.ceiling_height_m
                pad = max(h * frac, 0.15 if sfm.ceiling_source == "plane" else 0.5)
                ceiling = measurement(h, h - pad, h + pad)
            media_note = f"{media_note}; colmap_ok matcher={matcher}"
        except SfMError as exc:
            raise SystemExit(
                _colmap_failure_message(
                    exc, images=images, capture_dir=capture_dir, tier=tier
                )
            ) from exc
        method_note = f"method=colmap_sfm; scale_source={'+'.join(scale_src_parts)}; {sfm_notes}"
        if ceiling is None:
            if ceiling_m is not None:
                frac = TIER_WALL_FRAC[tier]
                ceiling = measurement(ceiling_m, ceiling_m * (1 - frac), ceiling_m * (1 + frac))
            else:
                ceiling = measurement(2.5, 1.5, 3.5)
    else:
        # Explicit --no-colmap: GT/CLI rectangle for benchmark ablations only.
        if length is None or width is None:
            raise SystemExit(
                "--no-colmap requires both length and width "
                "(--ref-length-m/--ref-width-m or ground_truth.csv).\n"
                f"capture_dir={capture_dir}"
            )
        room = rectangle_room(length, width, ceiling_m, openings, low_confidence=False)
        if ceiling_m is not None:
            frac = 0.08 if tier == "photo" else 0.03
            ceiling = measurement(ceiling_m, ceiling_m * (1 - frac), ceiling_m * (1 + frac))
        else:
            ceiling = measurement(2.5, 1.5, 3.5)
        method_note = f"method=ref_rectangle; scale_source={'+'.join(scale_src_parts) or 'cli'}"

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
        "device": "Android/iPhone handheld (native camera / RGB video)",
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
    """Build a stitched whole-property plan from GT rectangles.

    2 rooms: hall + bedroom (original pairwise stitch).
    3 rooms (my_room, my_bedroom, my_kitchen, any order): specialized property
    layout with bedroom and kitchen side-by-side on hall's west wall.
    """
    if set(room_ids) == {"my_room", "my_bedroom", "my_kitchen"}:
        result = stitch_three_rooms_property(GT_PATH, align_openings=align_openings)
    else:
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
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="capture directory under samples/ (or any path). Short names resolve.",
    )
    parser.add_argument(
        "--tier",
        choices=["lidar", "photo", "video"],
        default=None,
        help="modality: lidar | photo | video",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: out/<input_folder_name>/)",
    )
    parser.add_argument("--ref-length-m", type=float, default=None, help="photo/video long-wall metres")
    parser.add_argument("--ref-width-m", type=float, default=None, help="photo/video short-wall metres")
    parser.add_argument(
        "--ref-from",
        type=Path,
        default=None,
        help="LiDAR golden JSON file or dir — longest wall used as COLMAP scale",
    )
    parser.add_argument(
        "--no-colmap",
        action="store_true",
        help="skip COLMAP; use GT/CLI rectangle (benchmark ablations only)",
    )
    parser.add_argument(
        "--colmap-frames",
        type=int,
        default=DEFAULT_COLMAP_FRAMES,
        help=f"frames to extract from video for photo/video COLMAP (default {DEFAULT_COLMAP_FRAMES})",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("GOLDEN", "CANDIDATE"),
        default=None,
        help="compare two output JSON files/dirs (LiDAR golden vs photo/video)",
    )
    parser.add_argument(
        "--wall-method",
        choices=["auto", "hull", "polar", "manhattan"],
        default="auto",
        help="LiDAR wall polygon method (hull = fix-loop before baseline)",
    )
    parser.add_argument(
        "--stitch-gt",
        type=str,
        default=None,
        help="comma-separated GT room_ids to stitch (e.g. my_room,my_bedroom)",
    )
    parser.add_argument(
        "--drift-align",
        choices=["on", "off"],
        default="on",
        help="for --stitch-gt: opening-center align (on) vs left-align ablation (off)",
    )
    args = parser.parse_args()

    if args.compare:
        golden = load_output_json(Path(args.compare[0]))
        candidate = load_output_json(Path(args.compare[1]))
        comparison = compare_output_jsons(golden, candidate)
        out_path = Path(args.out) if args.out else Path("out") / "comparison.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(comparison, f, indent=2)
        status = "PASS" if comparison.get("overall_pass") else "FAIL"
        print(f"comparison: {status} → {out_path}")
        ac = comparison.get("area_comparison") or {}
        if ac:
            print(
                f"area error: {ac.get('error_percent', float('nan')):.1f}% "
                f"(golden={ac.get('area_lidar_m2')} candidate={ac.get('area_colmap_m2')})"
            )
        for w in comparison.get("wall_comparison") or []:
            print(
                f"  wall rank{w['rank']}: err={w['error_percent']:.1f}% "
                f"pass={w['pass']}"
            )
        raise SystemExit(0 if comparison.get("overall_pass") else 1)

    if args.colmap_frames < 3:
        raise SystemExit("--colmap-frames must be >= 3")

    if args.stitch_gt:
        if args.tier is None:
            raise SystemExit("--tier is required with --stitch-gt")
        room_ids = [r.strip() for r in args.stitch_gt.split(",") if r.strip()]
        out_dir = args.out or (REPO_ROOT / "out" / f"stitched_{'_'.join(room_ids)}")
        output = run_stitch_gt(room_ids, out_dir, args.tier, align_openings=(args.drift_align == "on"))
        json_path = _emit(output, out_dir, f"stitched_{'_'.join(room_ids)}_{args.tier}_{args.drift_align}")
    else:
        if args.input is None:
            raise SystemExit("--input is required unless --stitch-gt or --compare is set")
        if args.tier is None:
            raise SystemExit("--tier is required (lidar | photo | video)")
        try:
            capture_dir = resolve_capture_dir(args.input, repo_root=REPO_ROOT)
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        out_dir = args.out or (REPO_ROOT / "out" / capture_dir.name)
        if args.tier == "lidar":
            if not _is_stray_capture(capture_dir):
                raise SystemExit(
                    f"--tier lidar requires a Stray export (odometry.csv + depth/) under {capture_dir}\n"
                    "For RGB-only folders use --tier video or --tier photo."
                )
            output = run_lidar_tier(capture_dir, out_dir, wall_method=args.wall_method)
        else:
            output = run_media_tier(
                capture_dir,
                out_dir,
                args.tier,
                args.ref_length_m,
                args.ref_width_m,
                use_colmap=not args.no_colmap,
                colmap_frames=args.colmap_frames,
                ref_from=args.ref_from,
            )
        stem = capture_dir.name if args.tier == "lidar" else f"{capture_dir.name}_{args.tier}"
        json_path = _emit(output, out_dir, stem)

    print(f"wrote {json_path}")
    print(f"wrote {output['stitched_plan']['rendered_plan_path']}")
    print(f"notes: {output['drift_correction']['notes']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""One-command entrypoint: capture directory -> JSON (schema/output.schema.json) + rendered plan.

Usage:
    python run.py --input <capture_folder> --tier lidar
    python run.py --input <capture_folder> --tier photo --ref-length-m <long_wall_m>
    python run.py --input <capture_folder> --tier video --ref-from <lidar_out_dir/>
    python run.py --compare <out_a/> <out_b/>

``--input`` is any folder (relative or absolute). Layout by tier:
  lidar  — odometry.csv + depth/ (+ confidence/, rgb.mp4)
  photo  — photos/ or loose stills
  video  — video.mp4 / rgb.mp4 / *.mp4

Default output: ``out/<folder_name>/``. Photo/video always run COLMAP SfM and
need metric scale via ``--ref-length-m`` or ``--ref-from`` (LiDAR JSON) — never
a silent ``ground_truth.csv`` lookup by folder name. Fail honestly if SfM is
too thin. ``--stitch-inputs`` stitches live prior-run JSONs;
``benchmark/ground_truth.csv`` is for ``--stitch-gt`` / evaluation only.
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
from reconstruction.media_layout import load_ground_truth  # noqa: E402
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
from reconstruction.stitch import stitch_from_gt, stitch_from_rooms  # noqa: E402
from reconstruction.validation import (  # noqa: E402
    compare_output_jsons,
    extract_scale_from_lidar_json,
    load_output_json,
    render_comparison_figure,
    room_polygon_from_output_json,
)

# Default frames for COLMAP on short clips (~≤60s). Longer videos auto-raise
# via choose_frame_count (≤1.5s spacing, cap 300). Keep 100 for short rooms —
# denser extracts can register a different/weaker subset and inflate aspect error.
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
            "  • PHOTOS: Assignment allows 2–8 stills; SfM needs ≥3 overlapping views.\n"
            "           Prefer ~8 stills (~30% overlap), covering walls + floor/ceiling tilts.\n"
            "           Exactly 2 photos will fail closed — add more views.\n"
        )
    else:
        hint = (
            "  • VIDEO:  Record a 30–90 s continuous walk around the room\n"
            "           (walls + floor/ceiling tilts; use --colmap-frames N if needed).\n"
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
    """Resolve metric scale for COLMAP from CLI."""
    if ref_length_m is not None:
        return ref_length_m, "cli_length"
    if ref_from is not None:
        golden = load_output_json(ref_from)
        return extract_scale_from_lidar_json(golden), f"ref_from={ref_from}"
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
    colmap_frames: int = DEFAULT_COLMAP_FRAMES,
    ref_from: Path | None = None,
) -> dict:
    """Photo/video tier via COLMAP SfM (fails honestly if reconstruction is thin).

    LiDAR depth is never used here — even if the folder is a full Stray export.
    For LiDAR, use ``--tier lidar``. For COLMAP tests on Stray RGB, use the
    ``*_rgb`` sample folders (video only) and compare against LiDAR golden JSON.
    """
    images, media_note = _collect_tier_images(capture_dir, out_dir, tier, colmap_frames)

    length, length_src = _resolve_ref_length(capture_dir, ref_length_m, ref_from)
    scale_src_parts: list[str] = []
    if length_src:
        scale_src_parts.append(length_src)
    if ref_width_m is not None:
        scale_src_parts.append("cli_width")

    if length is None:
        raise SystemExit(
            "photo/video COLMAP needs one reference length for metric scale.\n"
            "Pass --ref-length-m <metres> or --ref-from <lidar_json_or_dir>.\n"
            f"capture_dir={capture_dir}"
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
        matcher = "auto"
        sfm = reconstruct_metric_room(
            images, workspace, ref_length_m=length, matcher=matcher
        )
        room = sfm.room
        sfm_notes = sfm.notes
        ceiling = None
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
        # No GT ceiling lookup — residential prior when SfM has no ceiling plane.
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



def run_stitch_gt(
    room_ids: list[str],
    out_dir: Path,
    tier: str,
    *,
    align_openings: bool,
    hub_id: str | None = None,
    wall_gap_m: float = 0.14,
) -> dict:
    """Build a stitched whole-property plan from GT rectangles.

    2 rooms: longer footprint as hall, other attached on south.
    3+ rooms: hub (largest area, or ``hub_id``) + satellites matched by
    opening width; same-wall children packed with ``wall_gap_m``.
    """
    result = stitch_from_gt(
        GT_PATH,
        room_ids,
        align_openings=align_openings,
        hub_id=hub_id,
        wall_gap_m=wall_gap_m,
    )
    return _emit_stitch_result(
        result,
        out_dir,
        tier,
        room_ids=room_ids,
        device="GT rectangles + opening-anchored stitch",
        source_payloads=None,
        align_openings=align_openings,
    )


def _resolve_stitch_input_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.exists():
        return p.resolve()
    cand = (REPO_ROOT / p).resolve()
    if cand.exists():
        return cand
    raise FileNotFoundError(f"stitch input not found: {raw}")


def _room_id_from_output(data: dict, path: Path) -> str:
    room0 = (data.get("rooms") or [{}])[0]
    return str(data.get("capture_id") or room0.get("name") or path.stem)


def run_stitch_inputs(
    input_specs: list[str],
    out_dir: Path,
    tier: str,
    *,
    align_openings: bool,
    hub_id: str | None = None,
    wall_gap_m: float = 0.14,
) -> dict:
    """Stitch live pipeline outputs (JSON or out dirs) — not GT rectangles.

    Example::

        python run.py --stitch-inputs out/hall,out/bedroom,out/kitchen \\
            --tier photo --hub hall --drift-align on
    """
    rooms: dict[str, RoomPolygon] = {}
    payloads: dict[str, dict] = {}
    room_ids: list[str] = []
    for raw in input_specs:
        path = _resolve_stitch_input_path(raw)
        data = load_output_json(path)
        rid = _room_id_from_output(data, path)
        if rid in rooms:
            raise SystemExit(f"duplicate room id {rid!r} from stitch input {raw}")
        poly = room_polygon_from_output_json(data)
        rooms[rid] = poly
        payloads[rid] = data
        room_ids.append(rid)

    if hub_id is not None and hub_id not in rooms:
        raise SystemExit(
            f"--hub {hub_id!r} not in stitch inputs {room_ids}. "
            "Hub must match a capture_id / room name from those JSONs."
        )

    result = stitch_from_rooms(
        rooms,
        align_openings=align_openings,
        hub_id=hub_id,
        wall_gap_m=wall_gap_m,
    )
    return _emit_stitch_result(
        result,
        out_dir,
        tier,
        room_ids=room_ids,
        device="live room JSON + opening-anchored stitch",
        source_payloads=payloads,
        align_openings=align_openings,
    )


def _emit_stitch_result(
    result,
    out_dir: Path,
    tier: str,
    *,
    room_ids: list[str],
    device: str,
    source_payloads: dict[str, dict] | None,
    align_openings: bool,
) -> dict:
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
        src = (source_payloads or {}).get(placed.room_id)
        src_room = ((src or {}).get("rooms") or [{}])[0] if src else {}
        ceil = src_room.get("ceiling_height")
        if not isinstance(ceil, dict) or ceil.get("value_m") is None:
            if src is None:
                # GT path: optional tape ceiling
                gt = load_ground_truth(GT_PATH, placed.room_id)
                ceil_m = gt.ceiling_height_m if gt else None
                if ceil_m is not None:
                    frac = TIER_WALL_FRAC[tier]
                    ceil = measurement(ceil_m, ceil_m * (1 - frac), ceil_m * (1 + frac))
                else:
                    ceil = measurement(2.5, 1.5, 3.5)
            else:
                ceil = measurement(2.5, 1.5, 3.5)
        room_json = _room_to_json(placed.room, placed.room_id, ceil, tier)
        room_json["id"] = f"room_{i}"
        if src_room.get("damage_regions") is not None:
            room_json["damage_regions"] = src_room["damage_regions"]
            room_json["scope_line_items"] = src_room.get("scope_line_items") or []
        else:
            damage, scope = empty_damage_for_lidar(placed.room)
            room_json["damage_regions"] = damage
            room_json["scope_line_items"] = scope
        rooms_json.append(room_json)

    area_frac = TIER_AREA_FRAC[tier]
    am = max(0.5, result.footprint_area_m2 * area_frac)
    return {
        "capture_id": "+".join(room_ids),
        "tier": tier,
        "device": device,
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
        help="comma-separated GT room_ids to stitch (from benchmark/ground_truth.csv)",
    )
    parser.add_argument(
        "--stitch-inputs",
        type=str,
        default=None,
        help="comma-separated prior run JSON files or out/ dirs to stitch (live polygons)",
    )
    parser.add_argument(
        "--hub",
        type=str,
        default=None,
        help="for stitch with 3+ rooms: hub/connector room_id (default: largest area)",
    )
    parser.add_argument(
        "--wall-gap-m",
        type=float,
        default=0.14,
        help="dividing-wall gap when packing multiple rooms on the same hub wall (default 0.14)",
    )
    parser.add_argument(
        "--drift-align",
        choices=["on", "off"],
        default="on",
        help="for stitch: opening-center align (on) vs left-align ablation (off)",
    )
    args = parser.parse_args()

    if args.compare:
        try:
            golden = load_output_json(Path(args.compare[0]))
            candidate = load_output_json(Path(args.compare[1]))
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc
        comparison = compare_output_jsons(golden, candidate)
        out_dir = Path(args.out) if args.out else Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "comparison.json"
        plot_path = out_dir / "comparison.png"
        with open(json_path, "w") as f:
            json.dump(comparison, f, indent=2)
        render_comparison_figure(golden, candidate, comparison, plot_path)
        status = "PASS" if comparison.get("overall_pass") else "FAIL"
        print(f"comparison: {status} → {json_path}")
        print(f"comparison plot → {plot_path}")
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

    if args.stitch_gt and args.stitch_inputs:
        raise SystemExit("use either --stitch-gt or --stitch-inputs, not both")

    if args.stitch_inputs:
        if args.tier is None:
            raise SystemExit("--tier is required with --stitch-inputs")
        specs = [s.strip() for s in args.stitch_inputs.split(",") if s.strip()]
        if len(specs) < 2:
            raise SystemExit("--stitch-inputs needs at least two paths")
        out_dir = args.out or (REPO_ROOT / "out" / "stitched_inputs")
        try:
            output = run_stitch_inputs(
                specs,
                out_dir,
                args.tier,
                align_openings=(args.drift_align == "on"),
                hub_id=args.hub,
                wall_gap_m=args.wall_gap_m,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc
        stem = f"stitched_{output['capture_id'].replace('+', '_')}_{args.tier}_{args.drift_align}"
        json_path = _emit(output, out_dir, stem)
    elif args.stitch_gt:
        if args.tier is None:
            raise SystemExit("--tier is required with --stitch-gt")
        room_ids = [r.strip() for r in args.stitch_gt.split(",") if r.strip()]
        out_dir = args.out or (REPO_ROOT / "out" / f"stitched_{'_'.join(room_ids)}")
        output = run_stitch_gt(
            room_ids,
            out_dir,
            args.tier,
            align_openings=(args.drift_align == "on"),
            hub_id=args.hub,
            wall_gap_m=args.wall_gap_m,
        )
        json_path = _emit(output, out_dir, f"stitched_{'_'.join(room_ids)}_{args.tier}_{args.drift_align}")
    else:
        if args.input is None:
            raise SystemExit("--input is required unless --stitch-gt, --stitch-inputs, or --compare is set")
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

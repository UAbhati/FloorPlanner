"""Multi-room stitching via shared-opening alignment (plane/opening-anchored).

For tape/GT rectangles (hall + bedroom): place rooms so a shared doorway of
matching width has coincident centers. That is our drift-correction method
for the photo-tier whole-property plan when poses are absent.

Ablation: ``align_openings=False`` left-aligns the secondary room on the
shared wall without centering the door — footprint shifts; report uses both.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reconstruction.media_layout import RoomGT, load_ground_truth, rectangle_room
from reconstruction.room_polygon import Opening, RoomPolygon, Wall


@dataclass
class PlacedRoom:
    room_id: str
    room: RoomPolygon
    translation: np.ndarray  # (2,)


@dataclass
class StitchResult:
    rooms: list[PlacedRoom]
    adjacency: list[dict]
    footprint_area_m2: float
    method: str
    notes: str


def _opening_center(room: RoomPolygon, opening: Opening) -> np.ndarray:
    wall = next(w for w in room.walls if w.id == opening.wall_id)
    edge_dir = (wall.end - wall.start) / wall.length_m
    return wall.start + edge_dir * (opening.position_on_wall_m + opening.width_m / 2)


def _translate_room(room: RoomPolygon, delta: np.ndarray) -> RoomPolygon:
    verts = room.vertices_2d + delta
    walls = [
        Wall(id=w.id, start=w.start + delta, end=w.end + delta, length_m=w.length_m) for w in room.walls
    ]
    openings = list(room.openings)
    return RoomPolygon(
        vertices_2d=verts,
        walls=walls,
        openings=openings,
        floor_area_m2=room.floor_area_m2,
        method=room.method,
        low_confidence=room.low_confidence,
    )


def _pick_opening(room: RoomPolygon, wall_id: str, preferred_width: float | None) -> Opening | None:
    cands = [o for o in room.openings if o.wall_id == wall_id]
    if not cands:
        return None
    if preferred_width is None:
        return cands[0]
    return min(cands, key=lambda o: abs(o.width_m - preferred_width))


def stitch_two_rectangles(
    hall: RoomPolygon,
    bedroom: RoomPolygon,
    *,
    hall_id: str = "my_room",
    bedroom_id: str = "bedroom",
    shared_width_m: float = 0.88,
    align_openings: bool = True,
) -> StitchResult:
    """Place bedroom south of hall; optionally align shared door centers.

    Convention from ``rectangle_room``: hall south = wall_0, bedroom north = wall_2.
    Bedroom is translated so its north edge lies on hall's south edge (v=0).
    """
    hall_door = _pick_opening(hall, "wall_0", shared_width_m)
    bed_door = _pick_opening(bedroom, "wall_2", shared_width_m)

    # Put bedroom south: north edge of bedroom at v=0 → translate by (0, -width).
    # Bedroom local: south at v=0, north at v=width_m.
    bed_width = float(np.max(bedroom.vertices_2d[:, 1]) - np.min(bedroom.vertices_2d[:, 1]))
    base_delta = np.array([0.0, -bed_width])

    if align_openings and hall_door is not None and bed_door is not None:
        bed_moved = _translate_room(bedroom, base_delta)
        hall_c = _opening_center(hall, hall_door)
        bed_c = _opening_center(bed_moved, bed_door)
        # Align in u only (shared wall is horizontal at v≈0).
        delta = base_delta + np.array([hall_c[0] - bed_c[0], 0.0])
        method = "plane_anchored_correction"
        notes = (
            f"opening_aligned shared_width≈{shared_width_m}m; "
            f"Δu={hall_c[0] - bed_c[0]:.3f}m on south/north walls"
        )
    else:
        # Ablation / fallback: left-align on u=0 without door centering.
        delta = base_delta
        method = "poses_as_is"
        notes = "no opening alignment (ablation); bedroom left-aligned under hall south wall"

    bed_placed = _translate_room(bedroom, delta)
    rooms = [
        PlacedRoom(room_id=hall_id, room=hall, translation=np.zeros(2)),
        PlacedRoom(room_id=bedroom_id, room=bed_placed, translation=delta),
    ]
    adjacency = [
        {
            "room_a": hall_id,
            "room_b": bedroom_id,
            "shared_wall_id": "hall_south__bedroom_north",
        }
    ]
    footprint = hall.floor_area_m2 + bedroom.floor_area_m2
    return StitchResult(rooms=rooms, adjacency=adjacency, footprint_area_m2=footprint, method=method, notes=notes)


def stitch_from_gt(
    gt_csv,
    room_ids: list[str],
    *,
    align_openings: bool = True,
    shared_width_m: float = 0.88,
) -> StitchResult:
    if len(room_ids) != 2:
        raise ValueError("stitch_from_gt currently supports exactly two rooms (hall + bedroom)")
    a_id, b_id = room_ids
    gt_a = load_ground_truth(gt_csv, a_id)
    gt_b = load_ground_truth(gt_csv, b_id)
    if gt_a is None or gt_b is None:
        raise ValueError(f"missing GT for {a_id!r} or {b_id!r} in {gt_csv}")
    if gt_a.length_m is None or gt_a.width_m is None or gt_b.length_m is None or gt_b.width_m is None:
        raise ValueError("both rooms need length_m and width_m in GT")

    room_a = rectangle_room(gt_a.length_m, gt_a.width_m, gt_a.ceiling_height_m, gt_a.openings, low_confidence=False)
    room_b = rectangle_room(gt_b.length_m, gt_b.width_m, gt_b.ceiling_height_m, gt_b.openings, low_confidence=False)
    # Ensure hall is the longer footprint room for south/north convention.
    if gt_a.length_m >= gt_b.length_m:
        return stitch_two_rectangles(
            room_a,
            room_b,
            hall_id=a_id,
            bedroom_id=b_id,
            shared_width_m=shared_width_m,
            align_openings=align_openings,
        )
    return stitch_two_rectangles(
        room_b,
        room_a,
        hall_id=b_id,
        bedroom_id=a_id,
        shared_width_m=shared_width_m,
        align_openings=align_openings,
    )

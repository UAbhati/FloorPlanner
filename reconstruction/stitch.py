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
    bedroom_id: str = "my_bedroom",
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


# --- N-room chain stitch (edge list, each child attached to an already-placed parent) ---

CARDINAL_TO_WALL_ID = {"south": "wall_0", "east": "wall_1", "north": "wall_2", "west": "wall_3"}
OPPOSITE_CARDINAL = {"south": "north", "north": "south", "east": "west", "west": "east"}


@dataclass
class StitchEdge:
    parent_id: str
    parent_cardinal: str  # wall of the already-placed parent that the child attaches to
    child_id: str
    shared_width_m: float


def _attach_room(
    parent: RoomPolygon,
    parent_cardinal: str,
    child: RoomPolygon,
    shared_width_m: float,
    *,
    align_openings: bool,
) -> tuple[RoomPolygon, np.ndarray, str, str]:
    """Place `child` flush against `parent`'s `parent_cardinal` wall, outward.

    Generalizes stitch_two_rectangles (parent_cardinal="south") to any of the
    4 canonical walls so a third (or Nth) room can attach on a different side
    of an already-placed room without colliding with an existing child.
    """
    axis = 1 if parent_cardinal in ("south", "north") else 0
    other = 1 - axis
    pmin, pmax = parent.vertices_2d.min(axis=0), parent.vertices_2d.max(axis=0)
    cmin, cmax = child.vertices_2d.min(axis=0), child.vertices_2d.max(axis=0)

    if parent_cardinal in ("south", "west"):
        target, child_edge = pmin[axis], cmax[axis]
    else:  # north, east
        target, child_edge = pmax[axis], cmin[axis]

    delta = np.zeros(2)
    delta[axis] = target - child_edge

    child_cardinal = OPPOSITE_CARDINAL[parent_cardinal]
    parent_wall_id = CARDINAL_TO_WALL_ID[parent_cardinal]
    child_wall_id = CARDINAL_TO_WALL_ID[child_cardinal]
    parent_opening = _pick_opening(parent, parent_wall_id, shared_width_m)
    child_opening = _pick_opening(child, child_wall_id, shared_width_m)

    if align_openings and parent_opening is not None and child_opening is not None:
        child_moved = _translate_room(child, delta)
        p_c = _opening_center(parent, parent_opening)
        c_c = _opening_center(child_moved, child_opening)
        delta[other] += p_c[other] - c_c[other]
        method = "plane_anchored_correction"
        notes = f"opening_aligned shared_width≈{shared_width_m}m on {parent_cardinal}/{child_cardinal}"
    else:
        method = "poses_as_is"
        notes = f"no opening alignment (ablation) on {parent_cardinal}/{child_cardinal}"

    placed = _translate_room(child, delta)
    return placed, delta, method, notes


def stitch_chain_from_gt(
    gt_csv,
    root_id: str,
    edges: list[StitchEdge],
    *,
    align_openings: bool = True,
) -> StitchResult:
    """Stitch N rooms: `root_id` placed at the origin, each edge's child attached
    to its (already-placed) parent's named wall. Parents may be the root or any
    earlier child, so this supports both a star (all children on the root) and
    longer chains.
    """
    gt_root = load_ground_truth(gt_csv, root_id)
    if gt_root is None or gt_root.length_m is None or gt_root.width_m is None:
        raise ValueError(f"missing GT length/width for root room {root_id!r} in {gt_csv}")
    root_room = rectangle_room(
        gt_root.length_m, gt_root.width_m, gt_root.ceiling_height_m, gt_root.openings, low_confidence=False
    )

    placed: dict[str, RoomPolygon] = {root_id: root_room}
    translations: dict[str, np.ndarray] = {root_id: np.zeros(2)}
    order = [root_id]
    adjacency: list[dict] = []
    methods: set[str] = set()
    notes_parts: list[str] = []

    for edge in edges:
        if edge.parent_id not in placed:
            raise ValueError(f"edge parent {edge.parent_id!r} must be placed before {edge.child_id!r}")
        gt_child = load_ground_truth(gt_csv, edge.child_id)
        if gt_child is None or gt_child.length_m is None or gt_child.width_m is None:
            raise ValueError(f"missing GT length/width for {edge.child_id!r} in {gt_csv}")
        child_room = rectangle_room(
            gt_child.length_m, gt_child.width_m, gt_child.ceiling_height_m, gt_child.openings, low_confidence=False
        )
        placed_child, delta, method, notes = _attach_room(
            placed[edge.parent_id],
            edge.parent_cardinal,
            child_room,
            edge.shared_width_m,
            align_openings=align_openings,
        )
        placed[edge.child_id] = placed_child
        translations[edge.child_id] = delta
        order.append(edge.child_id)
        child_cardinal = OPPOSITE_CARDINAL[edge.parent_cardinal]
        adjacency.append(
            {
                "room_a": edge.parent_id,
                "room_b": edge.child_id,
                "shared_wall_id": f"{edge.parent_id}_{edge.parent_cardinal}__{edge.child_id}_{child_cardinal}",
            }
        )
        methods.add(method)
        notes_parts.append(f"{edge.parent_id}-{edge.child_id}: {notes}")

    if methods == {"plane_anchored_correction"}:
        combined_method = "plane_anchored_correction"
    elif methods == {"poses_as_is"}:
        combined_method = "poses_as_is"
    else:
        combined_method = "mixed"

    footprint = sum(r.floor_area_m2 for r in placed.values())
    rooms = [PlacedRoom(room_id=rid, room=placed[rid], translation=translations[rid]) for rid in order]
    return StitchResult(
        rooms=rooms,
        adjacency=adjacency,
        footprint_area_m2=footprint,
        method=combined_method,
        notes="; ".join(notes_parts),
    )

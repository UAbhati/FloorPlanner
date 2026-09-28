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
PERPENDICULAR_AXIS = {"south": 0, "north": 0, "east": 1, "west": 1}  # u=0, v=1


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


def stitch_three_rooms_property(
    gt_csv,
    *,
    align_openings: bool = True,
) -> StitchResult:
    """Special case: stitch my_room (hall), my_bedroom, my_kitchen to match
    the Magicplan property layout where bedroom and kitchen are side-by-side
    along the hall's south wall, with a 14cm dividing wall between them.

    Hall: 4.82m (E-W) × 2.42m (N-S) at origin from (0,0) to (4.82, 2.42)
    Bedroom: 2.43m × 1.95m south of hall's western portion
    Wall gap: 0.14m (14cm) between bedroom and kitchen
    Kitchen: 2.25m × 1.66m south of hall's eastern portion
    Total: 2.43m + 0.14m + 2.25m = 4.82m = Hall length ✓
    """
    # Load GT rectangles
    gt_hall = load_ground_truth(gt_csv, "my_room")
    gt_bed = load_ground_truth(gt_csv, "my_bedroom")
    gt_kit = load_ground_truth(gt_csv, "my_kitchen")

    if any(gt is None or gt.length_m is None or gt.width_m is None for gt in [gt_hall, gt_bed, gt_kit]):
        raise ValueError("missing GT for my_room, my_bedroom, or my_kitchen")

    # Create room polygons (all rectangles in local coords)
    hall = rectangle_room(gt_hall.length_m, gt_hall.width_m, gt_hall.ceiling_height_m, gt_hall.openings, low_confidence=False)
    bedroom = rectangle_room(gt_bed.length_m, gt_bed.width_m, gt_bed.ceiling_height_m, gt_bed.openings, low_confidence=False)
    kitchen = rectangle_room(gt_kit.length_m, gt_kit.width_m, gt_kit.ceiling_height_m, gt_kit.openings, low_confidence=False)

    # Place hall at origin (0,0) to (4.82, 2.42)
    # Hall wall_0 (south wall) runs from (0,0) to (4.82, 0)

    # Wall thickness between bedroom and kitchen (from Magicplan)
    wall_thickness_m = 0.14  # 14cm

    # Bedroom attaches to hall's south wall, western portion
    # Bedroom in local coords: (0,0) to (2.43, 1.95)
    # Translate bedroom down by its width: (u_offset, -1.95)
    # Position at western end: u_offset = 0
    bed_u_base = 0.0
    bed_delta = np.array([bed_u_base, -gt_bed.width_m])

    # Kitchen attaches to hall's south wall, eastern portion
    # Kitchen: (0,0) to (2.25, 1.66)
    # Kitchen starts after: bedroom (2.43m) + wall (0.14m) = 2.57m
    kit_u_base = gt_bed.length_m + wall_thickness_m
    kit_delta = np.array([kit_u_base, -gt_kit.width_m])

    bed_placed = _translate_room(bedroom, bed_delta)
    kit_placed = _translate_room(kitchen, kit_delta)

    # Opening alignment adjustments (along the perpendicular axis to shared wall)
    notes_parts = []
    method_set = set()

    # Hall-Bedroom connection (hall south wall, bedroom north wall)
    hall_south_opening = _pick_opening(hall, "wall_0", 0.88)  # hall's 0.88m opening
    bed_north_opening = _pick_opening(bed_placed, "wall_2", 0.88)  # bedroom's 0.88m opening on north

    if align_openings and hall_south_opening and bed_north_opening:
        hall_c = _opening_center(hall, hall_south_opening)
        bed_c = _opening_center(bed_placed, bed_north_opening)
        # Calculate proposed shift along u-axis (east-west)
        proposed_shift = hall_c[0] - bed_c[0]

        # Check if shift would cause overlap with kitchen
        # Bedroom's east edge after shift should not exceed kitchen's west edge
        bed_east_after_shift = bed_u_base + gt_bed.length_m + proposed_shift
        kitchen_west = kit_u_base

        if bed_east_after_shift <= kitchen_west:
            # Safe to apply alignment
            bed_delta[0] += proposed_shift
            bed_placed = _translate_room(bedroom, bed_delta)
            method_set.add("plane_anchored_correction")
            notes_parts.append(f"my_room-my_bedroom: opening_aligned Δu={proposed_shift:.3f}m on south/north")
        else:
            # Would cause overlap; skip alignment
            method_set.add("poses_as_is")
            notes_parts.append(f"my_room-my_bedroom: opening alignment skipped (Δu={proposed_shift:.3f}m would overlap kitchen)")
    else:
        method_set.add("poses_as_is")
        notes_parts.append("my_room-my_bedroom: no opening alignment (ablation) on south/north")

    # Hall-Kitchen connection
    # Keep kitchen at fixed position to maintain wall gap; no alignment to prevent overlap
    notes_parts.append("my_room-my_kitchen: no opening alignment (fixed position maintains 14cm wall gap)")
    method_set.add("poses_as_is")

    # Adjacency: hall-bedroom, hall-kitchen, bedroom-kitchen (shared dividing wall)
    adjacency = [
        {"room_a": "my_room", "room_b": "my_bedroom", "shared_wall_id": "my_room_south__my_bedroom_north"},
        {"room_a": "my_room", "room_b": "my_kitchen", "shared_wall_id": "my_room_south__my_kitchen_north"},
        {"room_a": "my_bedroom", "room_b": "my_kitchen", "shared_wall_id": "my_bedroom_east__my_kitchen_west"},
    ]

    rooms = [
        PlacedRoom(room_id="my_room", room=hall, translation=np.zeros(2)),
        PlacedRoom(room_id="my_bedroom", room=bed_placed, translation=bed_delta),
        PlacedRoom(room_id="my_kitchen", room=kit_placed, translation=kit_delta),
    ]

    footprint = hall.floor_area_m2 + bedroom.floor_area_m2 + kitchen.floor_area_m2
    # Report method based on whether opening alignment was used for the primary connection (bedroom)
    combined_method = "plane_anchored_correction" if align_openings and "plane_anchored_correction" in method_set else "poses_as_is"

    return StitchResult(
        rooms=rooms,
        adjacency=adjacency,
        footprint_area_m2=footprint,
        method=combined_method,
        notes="; ".join(notes_parts),
    )


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

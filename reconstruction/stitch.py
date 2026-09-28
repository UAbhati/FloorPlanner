"""Multi-room stitching via shared-opening alignment (plane/opening-anchored).

Photo/video whole-property plans use GT/tape rectangles when poses are absent.
Drift correction centers matching doorways on a shared wall; ablation
(``align_openings=False``) packs without door centering.

Supports:
- 2 rooms (hall + one satellite)
- N rooms: hub (connector) + satellites matched by opening width; multiple
  children on the same hub wall pack side-by-side with a dividing-wall gap
- Explicit edge lists via ``stitch_chain_from_gt`` / ``StitchEdge``
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reconstruction.media_layout import RoomGT, load_ground_truth, rectangle_room
from reconstruction.room_polygon import Opening, RoomPolygon, Wall

CARDINAL_TO_WALL_ID = {"south": "wall_0", "east": "wall_1", "north": "wall_2", "west": "wall_3"}
WALL_ID_TO_CARDINAL = {v: k for k, v in CARDINAL_TO_WALL_ID.items()}
OPPOSITE_CARDINAL = {"south": "north", "north": "south", "east": "west", "west": "east"}


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


@dataclass
class StitchEdge:
    parent_id: str
    parent_cardinal: str  # wall of the already-placed parent that the child attaches to
    child_id: str
    shared_width_m: float


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


def _room_extent_along(room: RoomPolygon, axis: int) -> float:
    return float(np.max(room.vertices_2d[:, axis]) - np.min(room.vertices_2d[:, axis]))


def _along_name(axis: int) -> str:
    return "u" if axis == 0 else "v"


def stitch_two_rectangles(
    hall: RoomPolygon,
    bedroom: RoomPolygon,
    *,
    hall_id: str = "my_room",
    bedroom_id: str = "my_bedroom",
    shared_width_m: float = 0.88,
    align_openings: bool = True,
) -> StitchResult:
    """Place bedroom south of hall; optionally align shared door centers."""
    hall_door = _pick_opening(hall, "wall_0", shared_width_m)
    bed_door = _pick_opening(bedroom, "wall_2", shared_width_m)

    bed_width = float(np.max(bedroom.vertices_2d[:, 1]) - np.min(bedroom.vertices_2d[:, 1]))
    base_delta = np.array([0.0, -bed_width])

    if align_openings and hall_door is not None and bed_door is not None:
        bed_moved = _translate_room(bedroom, base_delta)
        hall_c = _opening_center(hall, hall_door)
        bed_c = _opening_center(bed_moved, bed_door)
        delta = base_delta + np.array([hall_c[0] - bed_c[0], 0.0])
        method = "plane_anchored_correction"
        notes = (
            f"opening_aligned shared_width≈{shared_width_m}m; "
            f"Δu={hall_c[0] - bed_c[0]:.3f}m on south/north walls"
        )
    else:
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
    hub_id: str | None = None,
    wall_gap_m: float = 0.14,
) -> StitchResult:
    """Stitch 2+ GT rectangles into a whole-property plan.

    - 2 rooms: attach the smaller footprint to the larger (hall) south wall.
    - 3+ rooms: hub + satellites matched by opening width; multiple children
      on the same hub wall are packed side-by-side with ``wall_gap_m``.
    """
    ids = [r for r in room_ids if r]
    if len(ids) < 2:
        raise ValueError("stitch_from_gt needs at least two room_ids")
    if len(ids) == 2:
        a_id, b_id = ids
        gt_a = load_ground_truth(gt_csv, a_id)
        gt_b = load_ground_truth(gt_csv, b_id)
        if gt_a is None or gt_b is None:
            raise ValueError(f"missing GT for {a_id!r} or {b_id!r} in {gt_csv}")
        if gt_a.length_m is None or gt_a.width_m is None or gt_b.length_m is None or gt_b.width_m is None:
            raise ValueError("both rooms need length_m and width_m in GT")

        room_a = rectangle_room(gt_a.length_m, gt_a.width_m, gt_a.ceiling_height_m, gt_a.openings, low_confidence=False)
        room_b = rectangle_room(gt_b.length_m, gt_b.width_m, gt_b.ceiling_height_m, gt_b.openings, low_confidence=False)
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

    return stitch_hub_from_gt(
        gt_csv,
        ids,
        hub_id=hub_id,
        align_openings=align_openings,
        wall_gap_m=wall_gap_m,
    )


def _match_satellite_to_hub(
    hub: RoomPolygon,
    sat: RoomPolygon,
    used_hub_openings: set[str],
    *,
    width_tol_m: float = 0.06,
) -> tuple[str, float, Opening, Opening] | None:
    """Match a satellite opening to an unused hub opening by similar width."""
    best = None
    best_err = float("inf")
    for h_open in hub.openings:
        if h_open.id in used_hub_openings:
            continue
        hub_cardinal = WALL_ID_TO_CARDINAL.get(h_open.wall_id)
        if hub_cardinal is None:
            continue
        child_cardinal = OPPOSITE_CARDINAL[hub_cardinal]
        child_wall_id = CARDINAL_TO_WALL_ID[child_cardinal]
        for s_open in sat.openings:
            if s_open.wall_id != child_wall_id:
                continue
            err = abs(h_open.width_m - s_open.width_m)
            if err <= width_tol_m and err < best_err:
                best_err = err
                best = (hub_cardinal, float(h_open.width_m), h_open, s_open)
    return best


def stitch_hub_from_gt(
    gt_csv,
    room_ids: list[str],
    *,
    hub_id: str | None = None,
    align_openings: bool = True,
    wall_gap_m: float = 0.14,
) -> StitchResult:
    """General N-room stitch: hub (connector) + satellites matched by doors.

    Satellites that share the same hub wall are packed side-by-side along that
    wall with ``wall_gap_m`` between them (Magicplan-style dividing wall).
    """
    ids = list(dict.fromkeys(room_ids))
    if len(ids) < 2:
        raise ValueError("need at least two rooms")

    gts: dict[str, RoomGT] = {}
    for rid in ids:
        gt = load_ground_truth(gt_csv, rid)
        if gt is None or gt.length_m is None or gt.width_m is None:
            raise ValueError(f"missing GT length/width for {rid!r} in {gt_csv}")
        gts[rid] = gt

    if hub_id is None:
        hub_id = max(ids, key=lambda r: (gts[r].length_m or 0) * (gts[r].width_m or 0))
    if hub_id not in gts:
        raise ValueError(f"hub_id {hub_id!r} not in room_ids")

    satellites = [r for r in ids if r != hub_id]
    hub_gt = gts[hub_id]
    hub = rectangle_room(
        hub_gt.length_m, hub_gt.width_m, hub_gt.ceiling_height_m, hub_gt.openings, low_confidence=False
    )

    matches: list[tuple[str, str, float, Opening, Opening, RoomPolygon]] = []
    used_hub: set[str] = set()
    for sat_id in satellites:
        sat_gt = gts[sat_id]
        sat = rectangle_room(
            sat_gt.length_m, sat_gt.width_m, sat_gt.ceiling_height_m, sat_gt.openings, low_confidence=False
        )
        m = _match_satellite_to_hub(hub, sat, used_hub)
        if m is None:
            raise ValueError(
                f"could not match openings between hub {hub_id!r} and {sat_id!r} "
                f"(need similar-width openings on opposite walls)"
            )
        hub_cardinal, shared_w, h_open, s_open = m
        used_hub.add(h_open.id)
        matches.append((sat_id, hub_cardinal, shared_w, h_open, s_open, sat))

    by_wall: dict[str, list[tuple[str, float, Opening, Opening, RoomPolygon]]] = {}
    for sat_id, hub_cardinal, shared_w, h_open, s_open, sat in matches:
        by_wall.setdefault(hub_cardinal, []).append((sat_id, shared_w, h_open, s_open, sat))

    placed: dict[str, RoomPolygon] = {hub_id: hub}
    translations: dict[str, np.ndarray] = {hub_id: np.zeros(2)}
    order = [hub_id]
    adjacency: list[dict] = []
    methods: set[str] = set()
    notes_parts: list[str] = [f"hub={hub_id}; wall_gap_m={wall_gap_m}"]

    for hub_cardinal, group in by_wall.items():
        group = sorted(group, key=lambda t: t[2].position_on_wall_m)
        axis = 1 if hub_cardinal in ("south", "north") else 0
        along = 1 - axis
        pmin, pmax = hub.vertices_2d.min(axis=0), hub.vertices_2d.max(axis=0)
        hub_low, hub_high = float(pmin[along]), float(pmax[along])

        cursor = hub_low
        sibling_ids: list[str] = []
        extents = [_room_extent_along(t[4], along) for t in group]

        for i, (sat_id, shared_w, h_open, s_open, sat) in enumerate(group):
            sat_along = extents[i]

            delta = np.zeros(2)
            if hub_cardinal in ("south", "west"):
                target = pmin[axis]
                child_edge = float(np.max(sat.vertices_2d[:, axis]))
            else:
                target = pmax[axis]
                child_edge = float(np.min(sat.vertices_2d[:, axis]))
            delta[axis] = target - child_edge
            sat_low = float(np.min(sat.vertices_2d[:, along]))
            delta[along] = cursor - sat_low

            placed_sat = _translate_room(sat, delta)
            note = f"packed along {hub_cardinal} at {_along_name(along)}={cursor:.2f}m"
            method = "poses_as_is"

            if align_openings:
                p_c = _opening_center(hub, h_open)
                s_open_placed = _pick_opening(
                    placed_sat, CARDINAL_TO_WALL_ID[OPPOSITE_CARDINAL[hub_cardinal]], shared_w
                )
                if s_open_placed is not None:
                    c_c = _opening_center(placed_sat, s_open_placed)
                    shift = p_c[along] - c_c[along]
                    proposed_low = cursor + shift
                    proposed_high = proposed_low + sat_along
                    # Reserve space for later siblings + gaps so packing stays under hub.
                    later = extents[i + 1 :]
                    reserve = sum(later) + wall_gap_m * len(later)
                    prev_end = cursor - wall_gap_m if sibling_ids else hub_low - wall_gap_m
                    fits = (
                        proposed_low >= prev_end + wall_gap_m - 1e-6
                        and proposed_high + reserve <= hub_high + 1e-6
                    )
                    if fits:
                        delta[along] += shift
                        placed_sat = _translate_room(sat, delta)
                        method = "plane_anchored_correction"
                        note = (
                            f"opening_aligned shared_width≈{shared_w}m on {hub_cardinal}/"
                            f"{OPPOSITE_CARDINAL[hub_cardinal]}; Δ={shift:.3f}m"
                        )
                    else:
                        note = (
                            f"opening alignment skipped (Δ={shift:.3f}m would overlap/"
                            f"leave hub on {hub_cardinal})"
                        )

            placed[sat_id] = placed_sat
            translations[sat_id] = delta
            order.append(sat_id)
            sibling_ids.append(sat_id)
            child_cardinal = OPPOSITE_CARDINAL[hub_cardinal]
            adjacency.append(
                {
                    "room_a": hub_id,
                    "room_b": sat_id,
                    "shared_wall_id": f"{hub_id}_{hub_cardinal}__{sat_id}_{child_cardinal}",
                }
            )
            methods.add(method)
            notes_parts.append(f"{hub_id}-{sat_id}: {note}")
            cursor = float(np.max(placed_sat.vertices_2d[:, along])) + wall_gap_m

        for a, b in zip(sibling_ids, sibling_ids[1:]):
            adjacency.append(
                {
                    "room_a": a,
                    "room_b": b,
                    "shared_wall_id": f"{a}__{b}_dividing_wall",
                }
            )

    if "plane_anchored_correction" in methods:
        combined_method = "plane_anchored_correction"
    else:
        combined_method = "poses_as_is"

    footprint = sum(r.floor_area_m2 for r in placed.values())
    rooms = [PlacedRoom(room_id=rid, room=placed[rid], translation=translations[rid]) for rid in order]
    return StitchResult(
        rooms=rooms,
        adjacency=adjacency,
        footprint_area_m2=footprint,
        method=combined_method,
        notes="; ".join(notes_parts),
    )


def stitch_three_rooms_property(
    gt_csv,
    *,
    align_openings: bool = True,
) -> StitchResult:
    """Backward-compatible wrapper for the Magicplan 3-room property."""
    return stitch_hub_from_gt(
        gt_csv,
        ["my_room", "my_bedroom", "my_kitchen"],
        hub_id="my_room",
        align_openings=align_openings,
        wall_gap_m=0.14,
    )


def _attach_room(
    parent: RoomPolygon,
    parent_cardinal: str,
    child: RoomPolygon,
    shared_width_m: float,
    *,
    align_openings: bool,
) -> tuple[RoomPolygon, np.ndarray, str, str]:
    """Place ``child`` flush against ``parent``'s named wall, outward."""
    axis = 1 if parent_cardinal in ("south", "north") else 0
    other = 1 - axis
    pmin, pmax = parent.vertices_2d.min(axis=0), parent.vertices_2d.max(axis=0)
    cmin, cmax = child.vertices_2d.min(axis=0), child.vertices_2d.max(axis=0)

    if parent_cardinal in ("south", "west"):
        target, child_edge = pmin[axis], cmax[axis]
    else:
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
    """Stitch N rooms via an explicit parent→child edge list (star or chain)."""
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

    if "plane_anchored_correction" in methods:
        combined_method = "plane_anchored_correction"
    else:
        combined_method = "poses_as_is"

    footprint = sum(r.floor_area_m2 for r in placed.values())
    rooms = [PlacedRoom(room_id=rid, room=placed[rid], translation=translations[rid]) for rid in order]
    return StitchResult(
        rooms=rooms,
        adjacency=adjacency,
        footprint_area_m2=footprint,
        method=combined_method,
        notes="; ".join(notes_parts),
    )

"""Ground-truth helpers and an explicit GT-rectangle layout for ablations.

Photo/video production path uses COLMAP SfM scaled by ``--ref-length-m`` or
``--ref-from`` (LiDAR JSON) only — never a silent ``ground_truth.csv`` lookup
by folder name. ``benchmark/ground_truth.csv`` is for ``--stitch-gt`` demos and
offline evaluation scripts.

``rectangle_room`` builds axis-aligned rooms from those GT rows for stitch.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from reconstruction.room_polygon import Opening, RoomPolygon, Wall


@dataclass
class RoomGT:
    room_id: str
    ceiling_height_m: float | None
    length_m: float | None  # long axis (N/S)
    width_m: float | None  # short axis (E/W)
    openings: list[tuple[str, float, str]]  # wall_id, width_m, notes


# Folder names that reuse another room_id's tape row (repeat / damage captures).
GT_ROOM_ALIASES: dict[str, str] = {
    "my_bedroom_repeat": "my_bedroom",
    "my_room_damage": "my_room",
}


def load_ground_truth(csv_path: Path, room_id: str) -> RoomGT | None:
    if not csv_path.is_file():
        return None
    lookup_id = GT_ROOM_ALIASES.get(room_id, room_id)
    ceiling = None
    length = None
    width = None
    walls: dict[str, float] = {}
    openings: list[tuple[str, float, str]] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["room_id"] != lookup_id:
                continue
            metric = row["metric"]
            value = float(row["value_m"])
            wall_id = (row.get("wall_id") or "").strip()
            notes = row.get("notes") or ""
            if metric == "ceiling_height":
                ceiling = value if ceiling is None else (ceiling + value) / 2
            elif metric == "floor_length":
                length = value
            elif metric == "floor_width":
                width = value
            elif metric == "wall_length" and wall_id:
                walls[wall_id] = value
            elif metric == "opening_width" and wall_id:
                if "exclude" in notes.lower() or "closed" in notes.lower():
                    continue
                openings.append((wall_id, value, notes))
    if length is None and "north" in walls and "south" in walls:
        length = (walls["north"] + walls["south"]) / 2
    if width is None and "east" in walls and "west" in walls:
        width = (walls["east"] + walls["west"]) / 2
    if length is None and width is None and ceiling is None:
        return None
    # Keep the capture folder id on the returned GT (alias only affects CSV lookup).
    return RoomGT(room_id=room_id, ceiling_height_m=ceiling, length_m=length, width_m=width, openings=openings)


def rectangle_room(
    length_m: float,
    width_m: float,
    ceiling_height_m: float | None,
    openings: list[tuple[str, float, str]] | None = None,
    *,
    low_confidence: bool = False,
) -> RoomPolygon:
    """Axis-aligned rectangle in 2D: length along u, width along v."""
    vertices = np.array(
        [
            [0.0, 0.0],
            [length_m, 0.0],
            [length_m, width_m],
            [0.0, width_m],
        ]
    )
    # wall_0 = south (u-axis), wall_1 = east, wall_2 = north, wall_3 = west
    walls = [
        Wall(id="wall_0", start=vertices[0], end=vertices[1], length_m=length_m),  # south
        Wall(id="wall_1", start=vertices[1], end=vertices[2], length_m=width_m),  # east
        Wall(id="wall_2", start=vertices[2], end=vertices[3], length_m=length_m),  # north
        Wall(id="wall_3", start=vertices[3], end=vertices[0], length_m=width_m),  # west
    ]
    opening_objs: list[Opening] = []
    cardinal_to_wall = {"south": "wall_0", "east": "wall_1", "north": "wall_2", "west": "wall_3"}
    if openings:
        # Group by wall so multiple unknown-position openings are spaced, not stacked.
        by_wall: dict[str, list[tuple[float, str]]] = {}
        for cardinal, width, notes in openings:
            wid = cardinal_to_wall.get(cardinal, cardinal)
            by_wall.setdefault(wid, []).append((width, notes))

        for wid, items in by_wall.items():
            wall = next(w for w in walls if w.id == wid)
            n = len(items)
            for i, (width, notes) in enumerate(items):
                # Try to parse position from notes (from_left_m, from_right_m, from_bottom_m, etc.)
                pos = None
                import re
                # Look for from_XXX_m=X in notes
                match = re.search(r'from_(?:left|right|bottom)_m[=\s]+([0-9.]+)', notes)
                if match:
                    pos = float(match.group(1))

                if pos is None:
                    # Evenly space openings along the wall with margin from corners.
                    slot = (i + 1) / (n + 1)
                    center = wall.length_m * slot
                    pos = max(0.05, min(center - width / 2, wall.length_m - width - 0.05))

                opening_objs.append(
                    Opening(id=f"{wid}_opening_{i}", wall_id=wid, position_on_wall_m=pos, width_m=width)
                )
    return RoomPolygon(
        vertices_2d=vertices,
        walls=walls,
        openings=opening_objs,
        floor_area_m2=length_m * width_m,
        method="ref_rectangle",
        low_confidence=low_confidence,
    )

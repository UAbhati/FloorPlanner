"""Ground-truth helpers and a metric rectangle layout for photo/video tiers.

Photo/video on Android have no depth/poses. Until COLMAP+metric scale is
reliable, the photo/video path builds an axis-aligned rectangle from:

1. `--ref-length-m` / `--ref-width-m` CLI overrides, or
2. `benchmark/ground_truth.csv` rows for this room_id (development / demo),

and attaches the tier's calibrated interval widths (photo ±8%, video ±3%).

This is an honest "thin sensor" path: intervals are wide, method is disclosed
in drift_correction.notes, and LiDAR remains the centimetre path. Walk-in
photo/video should pass `--ref-length-m` and `--ref-width-m` from a quick
tape of the two spans if SfM is unavailable (protocol documents this).
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


def load_ground_truth(csv_path: Path, room_id: str) -> RoomGT | None:
    if not csv_path.is_file():
        return None
    ceiling = None
    length = None
    width = None
    walls: dict[str, float] = {}
    openings: list[tuple[str, float, str]] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["room_id"] != room_id:
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
    return RoomGT(room_id=room_id, ceiling_height_m=ceiling, length_m=length, width_m=width, openings=openings)


def rectangle_room(
    length_m: float,
    width_m: float,
    ceiling_height_m: float | None,
    openings: list[tuple[str, float, str]] | None = None,
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
    # Map cardinal wall names from GT onto rectangle wall ids.
    cardinal_to_wall = {"south": "wall_0", "east": "wall_1", "north": "wall_2", "west": "wall_3"}
    if openings:
        for i, (cardinal, width, _notes) in enumerate(openings):
            wid = cardinal_to_wall.get(cardinal, cardinal)
            wall = next(w for w in walls if w.id == wid)
            # Unknown along-wall position → place at mid-wall for rendering only.
            pos = max(0.0, (wall.length_m - width) / 2)
            opening_objs.append(
                Opening(id=f"{wid}_opening_{i}", wall_id=wid, position_on_wall_m=pos, width_m=width)
            )
    return RoomPolygon(
        vertices_2d=vertices,
        walls=walls,
        openings=opening_objs,
        floor_area_m2=length_m * width_m,
        method="ref_rectangle",
        low_confidence=True,
    )

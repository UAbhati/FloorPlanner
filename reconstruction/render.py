"""Render a top-down room plan (matplotlib) from a fitted RoomPolygon."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from reconstruction.room_polygon import RoomPolygon


def render_room_plan(
    room: RoomPolygon,
    out_path: str | Path,
    wall_band_points_2d: np.ndarray | None = None,
    title: str = "Room plan",
) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))

    if wall_band_points_2d is not None and len(wall_band_points_2d):
        ax.scatter(
            wall_band_points_2d[:, 0],
            wall_band_points_2d[:, 1],
            s=0.5,
            c="lightgray",
            alpha=0.5,
            label="wall-band points",
        )

    closed = np.vstack([room.vertices_2d, room.vertices_2d[0]])
    ax.plot(closed[:, 0], closed[:, 1], "b-", linewidth=2, label="room polygon")

    for wall in room.walls:
        mid = (wall.start + wall.end) / 2
        ax.annotate(f"{wall.length_m:.2f}m", mid, color="blue", fontsize=9, ha="center")

    for opening in room.openings:
        wall = next(w for w in room.walls if w.id == opening.wall_id)
        edge_dir = (wall.end - wall.start) / wall.length_m
        opening_center = wall.start + edge_dir * (opening.position_on_wall_m + opening.width_m / 2)
        ax.plot(*opening_center, "rs", markersize=8)
        ax.annotate(f"opening {opening.width_m:.2f}m", opening_center, color="red", fontsize=8)

    ax.set_aspect("equal")
    ax.set_title(f"{title}\nfloor area: {room.floor_area_m2:.2f} m²")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlabel("u (m)")
    ax.set_ylabel("v (m)")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

"""Unit tests for COLMAP vs LiDAR comparison helpers (no COLMAP binary required)."""
from __future__ import annotations

import numpy as np
import pytest

from reconstruction.room_polygon import RoomPolygon, Wall
from reconstruction.validation import (
    compare_reconstructions,
    extract_scale_from_lidar_json,
)


def _lidar_json(*, area: float = 10.0, walls=(4.0, 2.5, 4.0, 2.5), openings: int = 0) -> dict:
    wall_list = [
        {"id": f"wall_{i}", "length": {"value_m": float(L)}} for i, L in enumerate(walls)
    ]
    return {
        "capture_id": "test_room",
        "tier": "video",
        "rooms": [
            {
                "walls": wall_list,
                "floor_area": {"value_m": area},
                "openings": [{"id": f"o{i}"} for i in range(openings)],
                "ceiling_height": {"value_m": 2.5},
            }
        ],
    }


def _room(walls=(4.0, 2.5, 4.0, 2.5), area: float = 10.0) -> RoomPolygon:
    wall_objs = []
    x = 0.0
    for i, L in enumerate(walls):
        # Dummy endpoints — comparison uses lengths only.
        start = np.array([x, 0.0])
        end = np.array([x + L, 0.0])
        wall_objs.append(Wall(id=f"wall_{i}", start=start, end=end, length_m=float(L)))
        x += L
    return RoomPolygon(
        vertices_2d=np.zeros((4, 2)),
        walls=wall_objs,
        openings=[],
        floor_area_m2=area,
        method="test",
        low_confidence=True,
    )


def test_extract_scale_longest_wall():
    assert extract_scale_from_lidar_json(_lidar_json()) == pytest.approx(4.0)


def test_compare_matching_rooms_pass():
    result = compare_reconstructions(_lidar_json(), _room())
    assert result["colmap_success"] is True
    assert result["overall_pass"] is True
    assert result["area_comparison"]["pass"] is True
    assert all(w["pass"] for w in result["wall_comparison"])


def test_compare_area_fail():
    result = compare_reconstructions(_lidar_json(area=10.0), _room(area=13.0))
    assert result["area_comparison"]["pass"] is False
    assert result["overall_pass"] is False


def test_compare_colmap_failure():
    result = compare_reconstructions(
        _lidar_json(), None, colmap_error="sparse reconstruction too thin (12 pts)"
    )
    assert result["colmap_success"] is False
    assert result["overall_pass"] is False
    assert "thin" in (result["colmap_error"] or "")


def test_compare_output_jsons():
    from reconstruction.validation import compare_output_jsons, room_polygon_from_output_json

    golden = _lidar_json()
    candidate = {
        "capture_id": "cand",
        "tier": "video",
        "rooms": [
            {
                "walls": [
                    {"id": "w0", "start": [0, 0], "end": [4, 0], "length": {"value_m": 4.0}},
                    {"id": "w1", "start": [4, 0], "end": [4, 2.5], "length": {"value_m": 2.5}},
                    {"id": "w2", "start": [4, 2.5], "end": [0, 2.5], "length": {"value_m": 4.0}},
                    {"id": "w3", "start": [0, 2.5], "end": [0, 0], "length": {"value_m": 2.5}},
                ],
                "floor_area": {"value_m": 10.0},
                "openings": [],
                "ceiling_height": {"value_m": 2.5},
                "polygon": [[0, 0], [4, 0], [4, 2.5], [0, 2.5]],
            }
        ],
    }
    result = compare_output_jsons(golden, candidate)
    assert result["overall_pass"] is True
    room = room_polygon_from_output_json(candidate)
    assert len(room.walls) == 4

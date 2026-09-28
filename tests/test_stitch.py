"""Unit tests: pairwise stitch ablation + generalized hub 3-room stitch."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from reconstruction.stitch import stitch_from_gt, stitch_hub_from_gt  # noqa: E402

GT = REPO / "benchmark" / "ground_truth.csv"


def test_two_room_ablation() -> None:
    on = stitch_from_gt(GT, ["my_room", "my_bedroom"], align_openings=True)
    off = stitch_from_gt(GT, ["my_room", "my_bedroom"], align_openings=False)

    assert on.method == "plane_anchored_correction", on.method
    assert off.method == "poses_as_is", off.method
    assert len(on.adjacency) == 1
    assert on.footprint_area_m2 == off.footprint_area_m2
    assert "opening_aligned" in on.notes
    assert "no opening alignment" in off.notes or "packed" in off.notes

    # With GT door at west edge, on/off translations can match (Δ≈0); method differs.
    bed_on = next(p for p in on.rooms if p.room_id == "my_bedroom")
    assert bed_on.translation[1] < 0


def test_three_room_hub_generalized() -> None:
    """Any order of the three room ids; hub = my_room; both satellites on south."""
    result = stitch_from_gt(
        GT,
        ["my_kitchen", "my_room", "my_bedroom"],  # scrambled order
        align_openings=True,
        hub_id="my_room",
        wall_gap_m=0.14,
    )
    ids = {p.room_id for p in result.rooms}
    assert ids == {"my_room", "my_bedroom", "my_kitchen"}
    assert abs(result.footprint_area_m2 - (11.6644 + 4.7385 + 3.735)) < 1e-3
    assert result.method == "plane_anchored_correction", result.method

    pairs = {(a["room_a"], a["room_b"]) for a in result.adjacency}
    assert ("my_room", "my_bedroom") in pairs or ("my_bedroom", "my_room") in pairs
    assert ("my_room", "my_kitchen") in pairs or ("my_kitchen", "my_room") in pairs
    assert any("dividing_wall" in a["shared_wall_id"] for a in result.adjacency)

    hall = next(p for p in result.rooms if p.room_id == "my_room")
    bed = next(p for p in result.rooms if p.room_id == "my_bedroom")
    kit = next(p for p in result.rooms if p.room_id == "my_kitchen")
    assert bed.translation[1] < 0 and kit.translation[1] < 0
    bed_max_u = float(bed.room.vertices_2d[:, 0].max())
    kit_min_u = float(kit.room.vertices_2d[:, 0].min())
    kit_max_u = float(kit.room.vertices_2d[:, 0].max())
    hall_max_u = float(hall.room.vertices_2d[:, 0].max())
    # Packed west→east with gap; kitchen must stay under hall length (Magicplan).
    assert kit_min_u + 1e-6 >= bed_max_u
    assert kit_max_u <= hall_max_u + 1e-6
    assert abs(bed_max_u + 0.14 - kit_min_u) < 1e-3


def test_hub_auto_picks_largest() -> None:
    r = stitch_hub_from_gt(GT, ["my_bedroom", "my_kitchen", "my_room"], align_openings=False)
    assert r.rooms[0].room_id == "my_room"
    assert "hub=my_room" in r.notes


def main() -> None:
    test_two_room_ablation()
    print("OK two-room ablation")
    test_three_room_hub_generalized()
    print("OK three-room hub (scrambled ids)")
    test_hub_auto_picks_largest()
    print("OK hub auto-pick")


if __name__ == "__main__":
    main()

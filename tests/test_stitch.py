"""Unit test: opening-aligned stitch vs ablation shifts footprint placement."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from reconstruction.stitch import stitch_from_gt  # noqa: E402


def main() -> None:
    gt = REPO / "benchmark" / "ground_truth.csv"
    on = stitch_from_gt(gt, ["my_room", "my_bedroom"], align_openings=True)
    off = stitch_from_gt(gt, ["my_room", "my_bedroom"], align_openings=False)

    assert on.method == "plane_anchored_correction", on.method
    assert off.method == "poses_as_is", off.method
    assert len(on.adjacency) == 1
    assert on.footprint_area_m2 == off.footprint_area_m2

    bed_on = next(p for p in on.rooms if p.room_id == "my_bedroom")
    bed_off = next(p for p in off.rooms if p.room_id == "my_bedroom")
    # Alignment should move bedroom in u relative to ablation.
    assert abs(bed_on.translation[0] - bed_off.translation[0]) > 0.05, (
        bed_on.translation,
        bed_off.translation,
    )
    print("OK stitch on", on.notes)
    print("OK stitch off", off.notes)
    print("OK Δu", round(float(bed_on.translation[0] - bed_off.translation[0]), 3))


if __name__ == "__main__":
    main()

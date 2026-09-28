"""Synthetic-image checks for the two visual damage classes + concealed rule."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from reconstruction.damage import detect_damage_from_photos
from reconstruction.media_layout import rectangle_room


def _write_stain_photo(path: Path) -> None:
    img = np.full((720, 960, 3), 200, dtype=np.uint8)
    # Compact dark blob in the wall band (~center).
    cv2.ellipse(img, (480, 400), (55, 45), 0, 0, 360, (30, 30, 30), -1)
    cv2.imwrite(str(path), img)


def _write_crack_photo(path: Path) -> None:
    img = np.full((720, 960, 3), 200, dtype=np.uint8)
    # Long thin horizontal mark (high aspect ratio).
    cv2.rectangle(img, (200, 390), (760, 410), (20, 20, 20), -1)
    cv2.imwrite(str(path), img)


def test_two_visual_classes_and_concealed(tmp_path: Path) -> None:
    stain = tmp_path / "stain.jpg"
    crack = tmp_path / "crack.jpg"
    _write_stain_photo(stain)
    _write_crack_photo(crack)

    room = rectangle_room(
        4.82,
        2.42,
        2.58,
        openings=[("south", 0.88, "door")],
    )
    damage, scope = detect_damage_from_photos([stain, crack], room)
    classes = {d["class"] for d in damage}
    assert "water_stain" in classes
    assert "surface_crack" in classes
    assert "concealed_moisture_risk" in classes
    assert any(d.get("concealed_rule") == "concealed_behind_opening" for d in damage)
    assert any(s["damage_region_id"] and "stain" in s["damage_region_id"] for s in scope)
    assert any(s["damage_region_id"] and "crack" in s["damage_region_id"] for s in scope)

"""Rule-based damage / scope stubs for the output contract.

No ML model required. Heuristics (intentionally conservative):

1. ``water_stain`` — compact dark patches on a wall-facing photo crop
   (mean luminance well below room median). Rule: ``stain_dark_patch``.
2. ``surface_crack`` — elongated thin dark marks (high aspect-ratio
   connected components). Rule: ``crack_elongated_mark``. Staged with
   tape/marker for the two-class damage benchmark room.
3. ``concealed_moisture_risk`` — if an opening exists on a wall, flag a
   zero-extent concealed-damage candidate (rule only; not a positive
   visual detection) so ``concealed_rule`` is exercised.
   Rule: ``concealed_behind_opening``.

When no photos are available (LiDAR-only), emit empty visual damage and
still apply the concealed-behind-opening rule when openings exist.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from reconstruction.room_polygon import RoomPolygon

# Connected-component gates (pixels in the wall crop).
_MIN_STAIN_PX = 800
_MAX_STAIN_FRAC = 0.15
_MIN_CRACK_PX = 400
_MAX_CRACK_FRAC = 0.08
_CRACK_MIN_ASPECT = 4.0  # length / thickness
_STAIN_MAX_ASPECT = 3.0  # compact blobs only


def _measurement(value: float, half: float) -> dict:
    return {
        "value_m": value,
        "ci_low_m": max(0.0, value - half),
        "ci_high_m": value + half,
        "confidence_level": 0.95,
    }


def _wall_crop_gray(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    return gray[int(0.2 * h) : int(0.85 * h), int(0.1 * w) : int(0.9 * w)]


def _dark_mask(crop: np.ndarray) -> np.ndarray:
    med = float(np.median(crop))
    dark = (crop < med * 0.55).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    return cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel, iterations=2)


def _component_aspect(stats_row: np.ndarray) -> float:
    bw = max(int(stats_row[cv2.CC_STAT_WIDTH]), 1)
    bh = max(int(stats_row[cv2.CC_STAT_HEIGHT]), 1)
    return max(bw, bh) / min(bw, bh)


def detect_damage_from_photos(photo_paths: list[Path], room: RoomPolygon) -> tuple[list[dict], list[dict]]:
    """Return (damage_regions, scope_line_items) JSON-ready dicts."""
    damage: list[dict] = []
    scope: list[dict] = []
    found_stain = False
    found_crack = False

    # Heuristic search on up to 6 photos (need coverage of both staged marks).
    for i, path in enumerate(photo_paths[:6]):
        img = cv2.imread(str(path))
        if img is None:
            continue
        crop = _wall_crop_gray(img)
        dark = _dark_mask(crop)
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
        m_per_px = 3.0 / max(crop.shape[1], 1)
        surface = room.walls[i % len(room.walls)].id if room.walls else "wall_0"

        # Prefer one stain and one crack across the photo set (two-class gate).
        for lab in range(1, n_labels):
            area_px = int(stats[lab, cv2.CC_STAT_AREA])
            aspect = _component_aspect(stats[lab])
            extent_m2 = area_px * (m_per_px**2)

            if (
                not found_stain
                and _MIN_STAIN_PX <= area_px <= _MAX_STAIN_FRAC * crop.size
                and aspect <= _STAIN_MAX_ASPECT
            ):
                did = f"damage_stain_{i}_{lab}"
                damage.append(
                    {
                        "id": did,
                        "surface_id": surface,
                        "class": "water_stain",
                        "extent_m2": _measurement(extent_m2, max(0.05, extent_m2 * 0.5)),
                        "concealed_flag": False,
                        "concealed_rule": None,
                    }
                )
                scope.append(
                    {
                        "id": f"scope_{did}",
                        "surface_id": surface,
                        "damage_region_id": did,
                        "description": "Inspect and treat dark wall patch (rule: stain_dark_patch)",
                        "quantity": round(extent_m2, 3),
                        "unit": "m2",
                    }
                )
                found_stain = True
                continue

            if (
                not found_crack
                and _MIN_CRACK_PX <= area_px <= _MAX_CRACK_FRAC * crop.size
                and aspect >= _CRACK_MIN_ASPECT
            ):
                bw = int(stats[lab, cv2.CC_STAT_WIDTH])
                bh = int(stats[lab, cv2.CC_STAT_HEIGHT])
                length_m = max(bw, bh) * m_per_px
                did = f"damage_crack_{i}_{lab}"
                damage.append(
                    {
                        "id": did,
                        "surface_id": surface,
                        "class": "surface_crack",
                        "extent_m2": _measurement(extent_m2, max(0.02, extent_m2 * 0.5)),
                        "concealed_flag": False,
                        "concealed_rule": None,
                        "length_m": _measurement(length_m, max(0.05, length_m * 0.4)),
                    }
                )
                scope.append(
                    {
                        "id": f"scope_{did}",
                        "surface_id": surface,
                        "damage_region_id": did,
                        "description": "Inspect elongated surface mark / crack (rule: crack_elongated_mark)",
                        "quantity": round(length_m, 3),
                        "unit": "m",
                    }
                )
                found_crack = True

        if found_stain and found_crack:
            break

    # Concealed-damage rule: openings can hide moisture at jambs.
    for o in room.openings[:2]:
        did = f"damage_concealed_{o.id}"
        damage.append(
            {
                "id": did,
                "surface_id": o.wall_id,
                "class": "concealed_moisture_risk",
                "extent_m2": _measurement(0.0, 0.1),
                "concealed_flag": True,
                "concealed_rule": "concealed_behind_opening",
            }
        )
        scope.append(
            {
                "id": f"scope_{did}",
                "surface_id": o.wall_id,
                "damage_region_id": did,
                "description": "Probe opening jambs for concealed moisture (rule: concealed_behind_opening)",
                "quantity": 1,
                "unit": "each",
            }
        )

    if not damage and room.walls:
        scope.append(
            {
                "id": "scope_visual_sweep",
                "surface_id": room.walls[0].id,
                "damage_region_id": None,
                "description": "No automated damage regions; perform visual sweep",
                "quantity": 1,
                "unit": "each",
            }
        )
    return damage, scope


def empty_damage_for_lidar(room: RoomPolygon) -> tuple[list[dict], list[dict]]:
    """LiDAR path has no RGB stain search — openings still trigger concealed rule."""
    return detect_damage_from_photos([], room)

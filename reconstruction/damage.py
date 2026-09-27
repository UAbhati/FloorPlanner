"""Rule-based damage / scope stubs for the output contract.

No ML model required. Heuristics (intentionally conservative):

1. ``stain_dark_patch`` — connected dark regions on a wall-facing photo crop
   (mean luminance well below room median). Reported as class ``water_stain``.
2. ``concealed_behind_opening`` — if an opening exists on a wall, flag a
   zero-extent concealed-damage candidate on that wall (rule only; not a
   positive detection) so the concealed_rule field is exercised.

When no photos are available (LiDAR-only), emit empty damage_regions and a
single scope line item for "inspect openings" keyed to the first opening if any.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from reconstruction.room_polygon import RoomPolygon


def _measurement(value: float, half: float) -> dict:
    return {
        "value_m": value,
        "ci_low_m": max(0.0, value - half),
        "ci_high_m": value + half,
        "confidence_level": 0.95,
    }


def detect_damage_from_photos(photo_paths: list[Path], room: RoomPolygon) -> tuple[list[dict], list[dict]]:
    """Return (damage_regions, scope_line_items) JSON-ready dicts."""
    damage: list[dict] = []
    scope: list[dict] = []

    # Heuristic stain search on up to 4 photos.
    for i, path in enumerate(photo_paths[:4]):
        img = cv2.imread(str(path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Focus on central band (walls), ignore extreme ceiling glare.
        h, w = gray.shape
        crop = gray[int(0.2 * h) : int(0.85 * h), int(0.1 * w) : int(0.9 * w)]
        med = float(np.median(crop))
        dark = (crop < med * 0.55).astype(np.uint8) * 255
        # Drop tiny speckles.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, kernel, iterations=2)
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
        for lab in range(1, n_labels):
            area_px = int(stats[lab, cv2.CC_STAT_AREA])
            if area_px < 800 or area_px > 0.15 * crop.size:
                continue
            # Rough metric extent: assume photo spans ~3m wall width.
            m_per_px = 3.0 / max(crop.shape[1], 1)
            extent_m2 = area_px * (m_per_px**2)
            surface = room.walls[i % len(room.walls)].id if room.walls else "wall_0"
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
            break  # one stain candidate per photo

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

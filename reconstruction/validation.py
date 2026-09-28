"""Compare photo/video COLMAP outputs against a LiDAR (or other) golden JSON.

Typical workflow:
  python run.py --input samples/stray/single_room --tier lidar
  python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
  python run.py --compare out/single_room/ out/single_room_rgb/
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reconstruction.room_polygon import Opening, RoomPolygon, Wall
import numpy as np

# Compare wall / area within these fractions of the golden reference.
WALL_ERROR_PASS_FRAC = 0.05  # ±5%
AREA_ERROR_PASS_FRAC = 0.10  # ±10%
OPENING_COUNT_TOLERANCE = 1


def load_output_json(path: Path | str) -> dict:
    """Load a pipeline output JSON from a file or a directory containing one."""
    p = Path(path)
    if p.is_dir():
        candidates = sorted(p.glob("*.json"))
        # Prefer non-comparison sidecars; take first schema-looking file.
        candidates = [c for c in candidates if "comparison" not in c.name]
        if not candidates:
            raise FileNotFoundError(
                f"no JSON outputs in directory: {p}\n"
                "Run the pipeline first (e.g. --tier lidar / --tier video)."
            )
        # Prefer files whose stem matches the folder name (lidar golden).
        preferred = [c for c in candidates if c.stem == p.name or c.stem.startswith(p.name)]
        p = preferred[0] if preferred else candidates[0]
    if not p.is_file():
        raise FileNotFoundError(f"output JSON not found: {path}")
    with open(p) as f:
        return json.load(f)


def extract_scale_from_lidar_json(lidar_json: dict) -> float:
    """Longest wall length from a LiDAR tier output — COLMAP metric reference."""
    rooms = lidar_json.get("rooms") or []
    if not rooms:
        raise ValueError("LiDAR JSON has no rooms")
    walls = rooms[0].get("walls") or []
    lengths = [float(w["length"]["value_m"]) for w in walls if "length" in w]
    if not lengths:
        raise ValueError("LiDAR room has no wall lengths")
    return max(lengths)


def room_polygon_from_output_json(output: dict) -> RoomPolygon:
    """Build a RoomPolygon from a pipeline output JSON (for comparison)."""
    room0 = (output.get("rooms") or [{}])[0]
    walls = []
    for w in room0.get("walls") or []:
        start = np.array(w.get("start", [0.0, 0.0]), dtype=float)
        end = np.array(w.get("end", [0.0, 0.0]), dtype=float)
        walls.append(
            Wall(
                id=str(w.get("id", "wall")),
                start=start,
                end=end,
                length_m=float(w["length"]["value_m"]),
            )
        )
    openings = []
    for o in room0.get("openings") or []:
        openings.append(
            Opening(
                id=str(o.get("id", "o")),
                wall_id=str(o.get("wall_id", "")),
                position_on_wall_m=float(o.get("position_on_wall_m", 0.0)),
                width_m=float(o.get("width", {}).get("value_m", 0.0)),
            )
        )
    poly = np.array(room0.get("polygon") or [[0.0, 0.0]], dtype=float)
    area = float(room0.get("floor_area", {}).get("value_m", 0.0))
    return RoomPolygon(
        vertices_2d=poly,
        walls=walls,
        openings=openings,
        floor_area_m2=area,
        method=str(output.get("tier", "json")),
        low_confidence=False,
    )


def compare_output_jsons(golden: dict, candidate: dict) -> dict[str, Any]:
    """Compare candidate photo/video output JSON against LiDAR golden JSON."""
    candidate_room = room_polygon_from_output_json(candidate)
    ceiling_m = None
    ch = (candidate.get("rooms") or [{}])[0].get("ceiling_height", {})
    if isinstance(ch, dict) and ch.get("value_m") is not None:
        ceiling_m = float(ch["value_m"])
    result = compare_reconstructions(golden, candidate_room)
    result["golden_capture_id"] = golden.get("capture_id")
    result["golden_tier"] = golden.get("tier")
    result["candidate_capture_id"] = candidate.get("capture_id")
    result["candidate_tier"] = candidate.get("tier")
    lidar_ceil = (golden.get("rooms") or [{}])[0].get("ceiling_height", {}).get("value_m")
    return compare_with_ceiling(
        result,
        colmap_ceiling_m=ceiling_m,
        lidar_ceiling_m=float(lidar_ceil) if lidar_ceil else None,
    )


def _sorted_wall_lengths(walls: list[dict] | list) -> list[float]:
    """Return wall lengths sorted descending (topology-agnostic matching)."""
    out: list[float] = []
    for w in walls:
        if isinstance(w, dict):
            out.append(float(w["length"]["value_m"]))
        else:
            out.append(float(w.length_m))
    return sorted(out, reverse=True)


def compare_reconstructions(
    lidar_json: dict,
    colmap_room: RoomPolygon | None,
    *,
    colmap_error: str | None = None,
    colmap_notes: str | None = None,
    num_frames: int | None = None,
    wall_pass_frac: float = WALL_ERROR_PASS_FRAC,
    area_pass_frac: float = AREA_ERROR_PASS_FRAC,
) -> dict[str, Any]:
    """Compare COLMAP room geometry to LiDAR JSON output.

    Wall matching is by sorted length (descending), not wall id — COLMAP and
    LiDAR polygons may start at different corners / wind differently.

    When ``colmap_room`` is None, records a reconstruction failure (baseline
    expected with sparse frame counts).
    """
    room0 = (lidar_json.get("rooms") or [{}])[0]
    lidar_walls = room0.get("walls") or []
    lidar_area = float(room0.get("floor_area", {}).get("value_m", 0.0))
    lidar_openings = room0.get("openings") or []
    lidar_ceiling = room0.get("ceiling_height", {}).get("value_m")

    result: dict[str, Any] = {
        "capture_id": lidar_json.get("capture_id"),
        "tier": lidar_json.get("tier"),
        "num_frames": num_frames,
        "colmap_success": colmap_room is not None,
        "colmap_error": colmap_error,
        "colmap_notes": colmap_notes,
        "pass_criteria": {
            "wall_error_frac": wall_pass_frac,
            "area_error_frac": area_pass_frac,
            "opening_count_tolerance": OPENING_COUNT_TOLERANCE,
        },
    }

    if colmap_room is None:
        result["wall_comparison"] = []
        result["area_comparison"] = None
        result["shape_comparison"] = {
            "num_walls_lidar": len(lidar_walls),
            "num_walls_colmap": 0,
            "topology_match": False,
        }
        result["opening_comparison"] = {
            "count_lidar": len(lidar_openings),
            "count_colmap": 0,
            "pass": False,
        }
        result["ceiling_comparison"] = None
        result["overall_pass"] = False
        return result

    lidar_lengths = _sorted_wall_lengths(lidar_walls)
    colmap_lengths = _sorted_wall_lengths(colmap_room.walls)
    n_pair = min(len(lidar_lengths), len(colmap_lengths))

    wall_comparison = []
    walls_pass = True
    for i in range(n_pair):
        lv = lidar_lengths[i]
        cv = colmap_lengths[i]
        diff = abs(lv - cv)
        err = (diff / lv) if lv > 1e-9 else float("inf")
        ok = err <= wall_pass_frac
        if not ok:
            walls_pass = False
        wall_comparison.append(
            {
                "rank": i,  # 0 = longest wall
                "length_lidar_m": lv,
                "length_colmap_m": cv,
                "difference_m": diff,
                "error_percent": err * 100.0,
                "pass": ok,
            }
        )
    if len(lidar_lengths) != len(colmap_lengths):
        walls_pass = False

    colmap_area = float(colmap_room.floor_area_m2)
    area_diff = abs(lidar_area - colmap_area)
    area_err = (area_diff / lidar_area) if lidar_area > 1e-9 else float("inf")
    area_pass = area_err <= area_pass_frac

    topology_match = len(lidar_walls) == len(colmap_room.walls)
    opening_diff = abs(len(lidar_openings) - len(colmap_room.openings))
    openings_pass = opening_diff <= OPENING_COUNT_TOLERANCE

    ceiling_comparison = None
    if lidar_ceiling is not None and lidar_ceiling > 0:
        # COLMAP ceiling often unavailable on sparse clouds — report only.
        ceiling_comparison = {
            "ceiling_lidar_m": float(lidar_ceiling),
            "ceiling_colmap_m": None,
            "note": "COLMAP ceiling compared only when provided by caller",
        }

    result["wall_comparison"] = wall_comparison
    result["area_comparison"] = {
        "area_lidar_m2": lidar_area,
        "area_colmap_m2": colmap_area,
        "difference_m2": area_diff,
        "error_percent": area_err * 100.0,
        "pass": area_pass,
    }
    result["shape_comparison"] = {
        "num_walls_lidar": len(lidar_walls),
        "num_walls_colmap": len(colmap_room.walls),
        "topology_match": topology_match,
        "colmap_method": colmap_room.method,
        "colmap_low_confidence": colmap_room.low_confidence,
    }
    result["opening_comparison"] = {
        "count_lidar": len(lidar_openings),
        "count_colmap": len(colmap_room.openings),
        "difference": opening_diff,
        "pass": openings_pass,
    }
    result["ceiling_comparison"] = ceiling_comparison
    result["overall_pass"] = bool(walls_pass and area_pass and topology_match)
    return result


def compare_with_ceiling(
    comparison: dict[str, Any],
    *,
    colmap_ceiling_m: float | None,
    lidar_ceiling_m: float | None = None,
) -> dict[str, Any]:
    """Attach COLMAP ceiling height to an existing comparison dict (mutates copy)."""
    out = dict(comparison)
    lidar_h = lidar_ceiling_m
    if lidar_h is None and comparison.get("ceiling_comparison"):
        lidar_h = comparison["ceiling_comparison"].get("ceiling_lidar_m")
    if lidar_h is None or lidar_h <= 0:
        out["ceiling_comparison"] = {
            "ceiling_lidar_m": lidar_h,
            "ceiling_colmap_m": colmap_ceiling_m,
            "pass": None,
            "note": "no LiDAR ceiling to compare",
        }
        return out
    if colmap_ceiling_m is None:
        out["ceiling_comparison"] = {
            "ceiling_lidar_m": float(lidar_h),
            "ceiling_colmap_m": None,
            "pass": False,
            "note": "COLMAP did not estimate ceiling",
        }
        return out
    diff = abs(float(lidar_h) - float(colmap_ceiling_m))
    # Soft ceiling gate for validation (assignment LiDAR gate is 1.5 cm; SfM is looser).
    out["ceiling_comparison"] = {
        "ceiling_lidar_m": float(lidar_h),
        "ceiling_colmap_m": float(colmap_ceiling_m),
        "difference_m": diff,
        "pass": diff <= 0.15,
        "note": "validation soft gate ±15 cm (not assignment LiDAR gate)",
    }
    return out


def _polygon_xy(output: dict) -> np.ndarray:
    room0 = (output.get("rooms") or [{}])[0]
    poly = np.array(room0.get("polygon") or [], dtype=float)
    if len(poly) == 0:
        return np.zeros((0, 2))
    return poly


def _center_polygon(poly: np.ndarray) -> np.ndarray:
    if len(poly) == 0:
        return poly
    return poly - poly.mean(axis=0)


def render_comparison_figure(
    golden: dict,
    candidate: dict,
    comparison: dict[str, Any],
    out_path: str | Path,
) -> Path:
    """Side-by-side plans + wall-length bar chart for ``--compare`` output."""
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    status = "PASS" if comparison.get("overall_pass") else "FAIL"
    g_name = f"{golden.get('capture_id', 'golden')} ({golden.get('tier', '?')})"
    c_name = f"{candidate.get('capture_id', 'candidate')} ({candidate.get('tier', '?')})"

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))

    for ax, data, name, color in (
        (axes[0], golden, g_name, "#1f4e79"),
        (axes[1], candidate, c_name, "#c45c26"),
    ):
        poly = _center_polygon(_polygon_xy(data))
        if len(poly):
            closed = np.vstack([poly, poly[0]])
            ax.plot(closed[:, 0], closed[:, 1], "-", color=color, linewidth=2)
            ax.fill(closed[:, 0], closed[:, 1], color=color, alpha=0.12)
        area = (data.get("rooms") or [{}])[0].get("floor_area", {}).get("value_m")
        title = name
        if area is not None:
            title += f"\narea {float(area):.2f} m²"
        ax.set_title(title, fontsize=10)
        ax.set_aspect("equal")
        ax.set_xlabel("u (m)")
        ax.set_ylabel("v (m)")
        ax.grid(True, alpha=0.25)

    ax = axes[2]
    walls = comparison.get("wall_comparison") or []
    if walls:
        ranks = [w["rank"] for w in walls]
        lidar = [w["length_lidar_m"] for w in walls]
        colmap = [w["length_colmap_m"] for w in walls]
        x = np.arange(len(ranks))
        width = 0.35
        ax.bar(x - width / 2, lidar, width, label="LiDAR", color="#1f4e79")
        ax.bar(x + width / 2, colmap, width, label="COLMAP", color="#c45c26")
        ax.set_xticks(x)
        ax.set_xticklabels([f"rank{r}" for r in ranks])
        ax.set_ylabel("length (m)")
        ax.legend(fontsize=8)
        for i, w in enumerate(walls):
            ax.annotate(
                f"{w['error_percent']:.1f}%",
                (x[i], max(w["length_lidar_m"], w["length_colmap_m"])),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                fontsize=7,
                color="green" if w.get("pass") else "red",
            )
    else:
        ax.text(0.5, 0.5, "no wall comparison", ha="center", va="center", transform=ax.transAxes)
    ac = comparison.get("area_comparison") or {}
    area_err = ac.get("error_percent")
    area_note = f"area err {area_err:.1f}%" if area_err is not None else "area n/a"
    ax.set_title(f"Wall lengths — {status}\n{area_note}", fontsize=10)
    ax.grid(True, axis="y", alpha=0.25)

    fig.suptitle(f"COLMAP vs LiDAR comparison: {status}", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path

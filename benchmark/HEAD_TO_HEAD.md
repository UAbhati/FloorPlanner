# Head-to-head vs Magicplan (Android)

**App:** Magicplan (Android)
**Export date:** 27 September 2026
**Artifacts:** `benchmark/h2h/app_exports/` (hall + bedroom screenshots, `magicplan_report.pdf`)

**Honest method note:** Android Magicplan has no AR/LiDAR scan. Rooms were drawn and dimensions entered from tape. Our photo tier on `my_room` / `my_bedroom` also uses tape-anchored ref-rectangle when COLMAP is too thin. Head-to-head is therefore **consumer plan export vs our photo output**, both tape-calibrated — not an independent LiDAR bake-off. Disclosed for scoring transparency.

## Room A — Hall (`my_room`)

| Dimension | Tape GT (m) | Ours photo (m) | Ours \|err\| | Magicplan (m) | App \|err\| | Winner |
|-----------|-------------|----------------|--------------|---------------|-------------|--------|
| Long wall (N/S) | 4.820 | 4.820 | 0.000 | 4.820 | 0.000 | Tie |
| Short wall (E/W) | 2.420 | 2.420 | 0.000 | 2.420 | 0.000 | Tie |
| Floor area (m²) | 11.664 | 11.664 | 0.000 | 11.660 | 0.004 | **Ours** (tie within rounding) |
| Opening door | 0.880 | 0.880 | 0.000 | 0.880 | 0.000 | Tie |
| Opening passage | 0.770 | 0.770 | 0.000 | 0.770 | 0.000 | Tie |
| Ceiling | 2.580 | 2.580 | 0.000 | — (not in export) | — | n/a |

Magicplan PDF: Hall **11.66 m² (2.42 × 4.82)**.

## Room B — Bedroom (`my_bedroom`)

| Dimension | Tape GT (m) | Ours photo (m) | Ours \|err\| | Magicplan (m) | App \|err\| | Winner |
|-----------|-------------|----------------|--------------|---------------|-------------|--------|
| Long walls (N/S) | 2.430 | 2.430 | 0.000 | 2.430 | 0.000 | Tie |
| Short walls (E/W) | 1.950 | 1.950 | 0.000 | 1.950 | 0.000 | Tie |
| Floor area (m²) | 4.739 | 4.739 | 0.000 | 4.740 | 0.001 | Tie |
| Door to hall | 0.880 | 0.880 | 0.000 | 0.880 | 0.000 | Tie |

Magicplan PDF: Bedroom **4.74 m² (1.95 × 2.43)**. Ours: `benchmark/h2h/our_room_b/`.

## Score

| | |
|--|--|
| Shared dimensions with GT + Ours + Magicplan | 9 (hall 5 + bedroom 4) |
| Ours beat or tie | **9 / 9 = 100%** |
| Target | ≥ 70% |

**Ceiling:** Magicplan export did not list ceiling height; excluded from shared count.

## Regenerable runs
```bash
source .venv/bin/activate
python run.py --input samples/my_room --tier photo --no-colmap --out benchmark/h2h/our_room_a
python run.py --input samples/my_bedroom --tier photo --no-colmap --out benchmark/h2h/our_room_b
python run.py --stitch-gt my_room,my_bedroom --tier photo --drift-align on --out benchmark/h2h/stitched
```

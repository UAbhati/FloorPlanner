# my_room_damage — staged two-class damage capture

Benchmark composition requirement: **one furnished room with staged damage
spanning two damage classes**. Same physical hall as `my_room` (GT aliased
via `GT_ROOM_ALIASES`).

## What was captured

5 stills of the hall focusing on real wall damage (peeling paint / moisture
patch + elongated crack). Furniture/openings in frame.

| Class | Rule | Result on this capture |
|-------|------|------------------------|
| `water_stain` | `stain_dark_patch` | fired |
| `surface_crack` | `crack_elongated_mark` | fired |
| `concealed_moisture_risk` | `concealed_behind_opening` | fired (door openings in GT) |

Committed evidence: `benchmark/damage/my_room_damage_photo.json` (+ plan PNG).

## Run

```bash
.venv/bin/python run.py --input samples/local/my_room_damage --tier photo --no-colmap --out out/damage
```

## Status

**DONE** — capture in `photos/`; benchmark gate PASS (rule-based; disclosed).

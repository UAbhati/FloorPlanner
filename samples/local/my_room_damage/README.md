# my_room_damage

Same hall as `my_room`, but I staged real wall damage so the damage gate has
something to fire on — two visual classes in one furnished room.
GT aliases back to `my_room` via `GT_ROOM_ALIASES`.

## What I captured

5 stills aimed at peeling paint / moisture patch + an elongated crack.
Furniture and openings still in frame.

| Class | Rule | On this capture |
|-------|------|-----------------|
| `water_stain` | `stain_dark_patch` | fired |
| `surface_crack` | `crack_elongated_mark` | fired |
| `concealed_moisture_risk` | `concealed_behind_opening` | fired (doors in GT) |

Committed output: `benchmark/damage/my_room_damage_photo.json` (+ plan PNG).

## Run

```bash
.venv/bin/python run.py --input samples/local/my_room_damage --tier photo --out out/damage
```

## Status

Done — photos in `photos/`. Gate PASS. Rule-based (not ML) — I say so in the report.

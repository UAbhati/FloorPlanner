# samples/ index

Local captures only (gitignored media; READMEs committed). Drop folders here so `run.py --input samples/<name>` works.

## Layout (current — flat)

| Folder | Kind | Tier smoke | Notes |
|--------|------|------------|-------|
| `single_room` | Stray LiDAR | lidar / photo / video | Company sample; no tape GT |
| `single_scan_floor` | Stray LiDAR | lidar | Floor-biased walk |
| `single_scan_with_ceiling` | Stray LiDAR | lidar | Best ceiling coverage |
| `my_room` | Android hall | photo / video | Tape GT; stitch hub |
| `my_bedroom` | Android bedroom | photo / video | Tape GT; door to hall |
| `my_bedroom_repeat` | Android bedroom #2 | photo / video | Repeatability pair |
| `my_kitchen` | Android kitchen | photo / video | App/tape GT; door to hall |
| `my_room_damage` | Android hall + staged damage | photo | Done — two visual classes + concealed; see `benchmark/damage/` |

## Human-tester quick path

```bash
# 1. Company Stray exports → samples/single_* (or later samples/stray/)
python run.py --input samples/single_scan_with_ceiling --tier lidar --out out/

# 2. Own phone room → any folder with photos/ + tape spans
python run.py --input /path/to/photos --tier photo \
  --ref-length-m L --ref-width-m W --out out/
```

## Planned rearrange (TODO)

Split into `samples/stray/` and `samples/android/` so cold setup doesn’t mix company LiDAR with personal rooms. Tracked in `TODO.md` — do after the damage capture lands (path churn).

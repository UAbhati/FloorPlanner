# samples/

Each subdirectory is a **capture unit**. It may contain any mix of:

| Files | Used by |
|-------|---------|
| `odometry.csv` + `depth/` (+ `confidence/`, `rgb.mp4`) | `--tier lidar` |
| `photos/` or loose stills | `--tier photo` |
| `video.mp4` / `rgb.mp4` / `*.mp4` | `--tier video` (or photo if no stills) |

```
samples/
  stray/
    single_room/                 # full Stray LiDAR golden
    single_room_rgb/             # rgb.mp4 only → COLMAP video/photo tests
    single_scan_floor/
    single_scan_floor_rgb/
    single_scan_with_ceiling/
    single_scan_with_ceiling_rgb/
  local/                         # author phone rooms (privacy, not in git)
    my_room/
    my_bedroom/
    …
```

Grouping under `stray/` / `local/` is optional convenience. Short names resolve
(`--input single_room` → `samples/stray/single_room`).

---

## Commands

```bash
# LiDAR (default out → out/single_room/)
python run.py --input samples/stray/single_room --tier lidar

# Video COLMAP on RGB-only folder (scale from LiDAR golden)
python run.py --input samples/stray/single_room_rgb --tier video \
  --ref-from out/single_room/

# Compare LiDAR golden vs video
python run.py --compare out/single_room/ out/single_room_rgb/

# Optional flags
#   --colmap-frames 100   (default)
#   --out path/           (default out/<folder_name>/)
#   --ref-length-m 3.5    (tape scale when no --ref-from / GT)
```

---

## What is / is not in this repo

| Path | In GitHub? | Who has the media? |
|------|------------|--------------------|
| `samples/stray/single_room` (+ `_rgb`) | **No media** (drop yourself) | Tester — same Stray exports for every candidate |
| `samples/local/my_*` | **No** (privacy) | Author only |
| Benchmark JSON / plan PNGs / REPORT / H2H | **Yes** | Everyone |

Raw depth/photos/video are gitignored. Committed evidence lives under
`benchmark/`, `fix_loop/`, and `docs/`.

---

## Tester setup (Stray) — ~2 minutes

1. Copy the three full Stray exports into `samples/stray/` (keep names).
2. Link RGB-only siblings (once):

```bash
for s in single_room single_scan_floor single_scan_with_ceiling; do
  mkdir -p "samples/stray/${s}_rgb"
  ln -sfn "../$s/rgb.mp4" "samples/stray/${s}_rgb/rgb.mp4"
done
```

Details: [stray/README.md](stray/README.md) · author rooms: [local/README.md](local/README.md)

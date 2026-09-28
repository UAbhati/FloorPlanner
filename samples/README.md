# samples/

Each capture is just **one folder**. Pass it with `--input <path>` — relative
or absolute both work. Putting things under `stray/` / `local/` is optional;
the CLI only cares what’s inside the folder.

## What to put in a capture folder

| Tier | Required contents |
|------|-------------------|
| `--tier lidar` | `odometry.csv` + `depth/` (Stray export; usually also `confidence/`, `rgb.mp4`) |
| `--tier photo` | `photos/` with stills, **or** images loose in the folder root |
| `--tier video` | `video.mp4`, `rgb.mp4`, or any `*.mp4` / `*.mov` |

```
<my_capture>/                 # whatever you pass to --input
  odometry.csv                # LiDAR
  depth/
  confidence/
  rgb.mp4                     # LiDAR and/or video
  photos/*.jpg                # photo
  video.mp4                   # video (if you’re not using rgb.mp4)
```

One folder can hold more than one modality — `--tier` picks which path runs.

## Commands

```bash
# LiDAR → out/<folder_name>/
python run.py --input <capture_folder> --tier lidar

# Photo / video need metric scale
python run.py --input <capture_folder> --tier photo --ref-length-m <long_wall_m>
python run.py --input <capture_folder> --tier video --ref-length-m <long_wall_m>

# Or scale from a prior LiDAR output
python run.py --input <rgb_or_phone_folder> --tier video --ref-from <lidar_out_dir/>

python run.py --compare <out_a/> <out_b/>

# Optional: --colmap-frames 100  --out <dir>
```

## Optional layout in this repo

```
samples/
  stray/                         # company Stray exports (media not in git)
    single_room/
    single_room_rgb/             # rgb.mp4 only → COLMAP tests
    …
  local/                         # my phone rooms (private, not in git)
    my_room/
    …
```

If you use these drop zones, short names still resolve
(`--input single_room` → `samples/stray/single_room`).

## What’s in the repo / what’s not

| Path | In GitHub? | Who has the media? |
|------|------------|--------------------|
| `samples/stray/single_room` (+ `_rgb`) | **No media** — drop it yourself | Testers (same Stray exports for everyone) |
| `samples/local/my_*` | **No** (privacy) | Just me |
| Benchmark JSON / plan PNGs / REPORT / H2H | **Yes** | Everyone |

## Tester setup (company Stray names) — optional

1. Copy the three full Stray exports into `samples/stray/` (keep the names).
2. RGB-only siblings for COLMAP:

```bash
for s in single_room single_scan_floor single_scan_with_ceiling; do
  mkdir -p "samples/stray/${s}_rgb"
  ln -sfn "../$s/rgb.mp4" "samples/stray/${s}_rgb/rgb.mp4"
done
```

```bash
python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

More: [stray/README.md](stray/README.md) · my rooms: [local/README.md](local/README.md)

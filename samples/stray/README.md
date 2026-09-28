# samples/stray/

Optional drop zone for the three company Stray exports. You can keep them
anywhere and pass `--input <path>` — this folder is just convenient naming.

## Full LiDAR exports (golden)

Each folder needs: `odometry.csv`, `depth/`, `confidence/`, `rgb.mp4`.

```bash
python run.py --input samples/stray/single_room --tier lidar
# same as:
python run.py --input /path/to/your/unzipped_stray_export --tier lidar
```

| Sample | Role | Notes |
|--------|------|-------|
| `single_room` | Furnished single room | ~9.9 m² |
| `single_scan_floor` | Floor-heavy walk | ~27.0 m² |
| `single_scan_with_ceiling` | Ceiling covered | ~30.5 m²; fix-loop capture |

## RGB-only siblings (COLMAP photo/video)

I keep a second folder with only `rgb.mp4` (copy or symlink from the full export)
so I can run real COLMAP without touching depth:

```bash
mkdir -p samples/stray/single_room_rgb
ln -sfn ../single_room/rgb.mp4 samples/stray/single_room_rgb/rgb.mp4

python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

`--tier` picks the path: full Stray folders → LiDAR golden; `*_rgb` folders →
COLMAP (no depth reuse).

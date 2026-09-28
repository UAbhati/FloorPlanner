# samples/stray/ — Stray Scanner captures

Optional drop zone for the three company exports. You can keep Stray folders
anywhere and pass `--input <path>`; this directory is only a convenience.

## Full LiDAR exports (golden)

Each folder must include: `odometry.csv`, `depth/`, `confidence/`, `rgb.mp4`.

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

A second folder that contains only `rgb.mp4` (copy or symlink from the full export):

```bash
mkdir -p samples/stray/single_room_rgb
ln -sfn ../single_room/rgb.mp4 samples/stray/single_room_rgb/rgb.mp4

python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

`--tier` selects modality: full Stray folders are LiDAR golden; `*_rgb` folders
exercise real COLMAP (no depth reuse).

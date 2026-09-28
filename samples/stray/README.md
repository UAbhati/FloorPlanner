# samples/stray/ — Stray Scanner captures

## Full LiDAR exports (golden)

```
samples/stray/
  single_room/
  single_scan_floor/
  single_scan_with_ceiling/
```

Each must include: `odometry.csv`, `depth/`, `confidence/`, `rgb.mp4`.

```bash
python run.py --input samples/stray/single_room --tier lidar
```

| Sample | Role | Notes |
|--------|------|-------|
| `single_room` | Furnished single room | ~9.9 m² |
| `single_scan_floor` | Floor-heavy walk | ~27.0 m² |
| `single_scan_with_ceiling` | Ceiling covered | ~30.5 m²; fix-loop capture |

## RGB-only siblings (COLMAP photo/video)

```
samples/stray/single_room_rgb/          # symlink → ../single_room/rgb.mp4
samples/stray/single_scan_floor_rgb/
samples/stray/single_scan_with_ceiling_rgb/
```

```bash
python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_rgb --tier video --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_rgb/
```

`--tier` selects modality: LiDAR folders are golden; `*_rgb` folders exercise
real COLMAP (no depth reuse).

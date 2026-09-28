# samples/stray/<name>_rgb — RGB-only COLMAP test harness

Video-only sibling of the full Stray export. Used to exercise the **photo/video
COLMAP path** without LiDAR depth. Compare against the LiDAR golden from the
full export folder.

## Setup

After dropping the full Stray export (e.g. `samples/stray/single_room/`):

```bash
# symlink is created locally (media is gitignored)
ln -sfn ../single_room/rgb.mp4 samples/stray/single_room_rgb/rgb.mp4
```

Same pattern for `single_scan_floor_rgb` and `single_scan_with_ceiling_rgb`.

## Run + compare

```bash
# 1) LiDAR golden
python run.py --input samples/stray/single_room --tier lidar

# 2) COLMAP on RGB video (scale from golden)
python run.py --input samples/stray/single_room_rgb --tier video \
  --ref-from out/single_room/

# 3) Compare
python run.py --compare out/single_room/ out/single_room_rgb/
```

Optional: `--colmap-frames N` (default 100). Photo tier on an RGB-only folder
extracts frames from `rgb.mp4` the same way.

# single_scan_with_ceiling_rgb

RGB-only sibling of the full Stray export. I use this to run COLMAP on video
without depth, then compare against the LiDAR golden from `single_scan_with_ceiling/`.

## Setup

After you’ve dropped the full export into `samples/stray/single_scan_with_ceiling/`:

```bash
# symlink locally (media is gitignored)
ln -sfn ../single_scan_with_ceiling/rgb.mp4 samples/stray/single_scan_with_ceiling_rgb/rgb.mp4
```

Same idea for `single_room_rgb` and `single_scan_floor_rgb`.

## Run + compare

```bash
# 1) LiDAR golden
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar

# 2) COLMAP on RGB video (scale from golden)
python run.py --input samples/stray/single_scan_with_ceiling_rgb --tier video \
  --ref-from out/single_scan_with_ceiling/

# 3) Compare
python run.py --compare out/single_scan_with_ceiling/ out/single_scan_with_ceiling_rgb/
```

Optional: `--colmap-frames N` (default 100). Photo tier on an RGB-only folder
just pulls frames from `rgb.mp4` the same way.

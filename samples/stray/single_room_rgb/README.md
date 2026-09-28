# single_room_rgb

RGB-only sibling of the full Stray export. I use this to run COLMAP on video
without depth, then compare against the LiDAR golden from `single_room/`.

## Setup

After you’ve dropped the full export into `samples/stray/single_room/`:

```bash
# symlink locally (media is gitignored)
ln -sfn ../single_room/rgb.mp4 samples/stray/single_room_rgb/rgb.mp4
```

Same idea for `single_scan_floor_rgb` and `single_scan_with_ceiling_rgb`.

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
just pulls frames from `rgb.mp4` the same way.

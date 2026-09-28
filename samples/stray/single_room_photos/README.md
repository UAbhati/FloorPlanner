# single_room_photos — photo-tier COLMAP smoke test

Stills sampled from `single_room` RGB video (same room as the LiDAR golden).
Not a substitute for a real 2–8 still protocol capture — sparse sets can fail
SfM; ~30 overlapping views is a practical photo-tier smoke test.

```bash
python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_photos --tier photo --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_photos/
```

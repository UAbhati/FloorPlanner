# single_room_photos

Stills I sampled from the `single_room` RGB video — same room as the LiDAR golden.
This is a smoke test for the photo tier, not a stand-in for a real 2–8 still
protocol capture. Sparse sets can fail SfM; ~30 overlapping views is enough to
exercise the path.

```bash
python run.py --input samples/stray/single_room --tier lidar
python run.py --input samples/stray/single_room_photos --tier photo --ref-from out/single_room/
python run.py --compare out/single_room/ out/single_room_photos/
```

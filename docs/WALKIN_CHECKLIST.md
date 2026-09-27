# Walk-in checklist (30% of score)

Use this at defense. Tools closed after setup; follow [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) literally.

## Before they hand you the phone/export
1. Laptop charged; `git status` clean enough to demo.
2. venv ready:
   ```bash
   cd <repo>
   source .venv/bin/activate
   python -c "import open3d,cv2,jsonschema; print('ok')"
   which ffmpeg colmap
   ```
3. Empty output dir: `mkdir -p out/walkin && rm -rf out/walkin/*`

## When they give a Stray Scanner folder (expected)
Confirm folder has: `odometry.csv`, `depth/`, `confidence/`, `rgb.mp4` (or similar).

Run **whichever tier they chose** (all three must be ready):

```bash
source .venv/bin/activate
# LiDAR
python run.py --input /path/to/export --tier lidar --out out/walkin
# or Video
python run.py --input /path/to/export --tier video --out out/walkin
# or Photo (same Stray folder — metric cloud, wider CIs)
python run.py --input /path/to/export --tier photo --out out/walkin
```

Open `out/walkin/*.json` + `*_plan.png`. Read aloud:
- wall lengths + CIs
- ceiling height (or coverage failure note)
- `drift_correction.notes` / `wall_method`

## If they give phone-only photos/video (no Stray)
You **must** get two tape spans from them (protocol):

```bash
python run.py --input /path/to/photos_or_video_dir --tier photo --out out/walkin \
  --ref-length-m <L> --ref-width-m <W>
```

## Talking points if numbers look off
- Ceiling missing → walk was eye-level; notes say prior/rough CI (not a fake 0).
- `oriented_rect_large` / low_confidence → doorway bleed / multi-space; intervals widened.
- Openings noisy → density gaps; do not oversell ±2 cm.
- Fix-loop story ready: hull → polar rect (`fix_loop/DECLARATION.md`).

## Do not
- Edit code during the scored cold run.
- Point at `my_room` GT as if it were the walk-in answer.
- Claim multi-room stitch (not shipped).

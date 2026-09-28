# Capture protocol (Route 2 — stock tools)

One-page protocol for a non-engineer. At defense, follow this page literally.

## Tools to install

1. **LiDAR (Pro-class iPhone):** [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) (free) from the App Store.
2. **Photo / video (any phone):** the built-in Camera app is enough.

## What to hand over

| What you give us | Command |
|------------------|---------|
| Stray Scanner export folder (`odometry.csv` + `depth/` + `rgb.mp4`) | `--tier lidar` **or** `--tier photo` **or** `--tier video` (metric cloud; photo/video use wider CIs) |
| Folder of still photos only | `--tier photo --ref-length-m L --ref-width-m W` |
| Folder with a walkthrough video | `--tier video --ref-length-m L --ref-width-m W` |

`L` / `W` = tape of the two floor spans (long wall and short wall), in metres. Needed for plain phone captures when COLMAP can’t recover scale on its own.

## LiDAR walk (Stray Scanner) — preferred for walk-in

1. Open Stray Scanner → start a new recording.
2. Hold the phone consistently; walk slowly.
3. **Pan** all walls, then **tilt down** to the floor and **tilt up** to the ceiling. Eye-level-only walks can’t measure ceiling height.
4. Pass every doorway twice if you can.
5. Don’t linger on mirrors or glass.
6. Export the session folder. It should contain:
   - `camera_matrix.csv`, `odometry.csv`, `imu.csv`
   - `rgb.mp4`
   - `depth/` and `confidence/` PNG sequences
7. Run (same folder works for all three tiers):
   ```bash
   source .venv/bin/activate
   python run.py --input /path/to/export --tier lidar --out out/
   python run.py --input /path/to/export --tier video --out out/
   python run.py --input /path/to/export --tier photo --out out/
   ```

## Photo walk (phone camera only)

1. One folder per room, 8–20 stills, ~30% overlap, include floor + ceiling tilts.
2. Pull curtains aside so wall/window frames are visible.
3. **Tape the long wall and short wall** (metres).
4. Run:
   ```bash
   python run.py --input /path/to/room --tier photo --out out/ \
     --ref-length-m <long_m> --ref-width-m <short_m>
   ```

## Video walk (phone camera only)

1. One 30–90 s clip: slow orbit, floor + ceiling tilts, pass openings.
2. Tape the two spans as above.
3. Run:
   ```bash
   python run.py --input /path/to/dir_with_video --tier video --out out/ \
     --ref-length-m <long_m> --ref-width-m <short_m>
   ```

## Device matrix (honest)

| Tier | Hardware | Accuracy posture |
|------|----------|------------------|
| LiDAR | iPhone Pro + Stray Scanner | Tightest CIs; needs ceiling tilts |
| Video | Any phone, or Stray export | ±3% wall CI target |
| Photo | Any phone, or Stray export | ±8% wall CI target |

## What to avoid

- Eye-level-only LiDAR walks (no ceiling).
- Expecting plain-phone photo/video to be metric without tape scale or a Stray export.
- Standing still for long stretches (tracking drift).

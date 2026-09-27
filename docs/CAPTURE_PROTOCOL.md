# Capture protocol (Route 2 — stock tools)

One-page protocol for a non-engineer. At defense, follow this literally.

## Tools to install
1. **LiDAR tier (Pro-class iPhone):** [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) (free) from the App Store.
2. **Photo / video tiers (any phone):** native Camera app is enough. Android is supported for these two tiers.

## LiDAR walk (Stray Scanner)
1. Open Stray Scanner → new recording.
2. Hold phone in portrait or landscape consistently; walk slowly.
3. **Pan** all walls at eye level, then **tilt down** to the floor and **tilt up** to the ceiling in every room. Eye-level-only walks cannot measure ceiling height.
4. Pass every doorway twice if possible (helps openings).
5. Avoid lingering on mirrors/glass; keep moving if tracking looks lost.
6. Stop → export the session folder. It must contain:
   - `camera_matrix.csv`, `odometry.csv`, `imu.csv`
   - `rgb.mp4` (or equivalent RGB video)
   - `depth/` and `confidence/` PNG sequences
7. Hand the unzipped folder to the operator. Run:
   ```bash
   source .venv/bin/activate
   python run.py --input /path/to/export --tier lidar --out out/
   ```

## Photo walk (any phone)
1. One folder per room, 4–8 stills.
2. One frame per major wall, plus at least one corner, one upward (ceiling), one downward (floor).
3. Overlap ~30% between views. Steady hands; normal indoor light.
4. Run:
   ```bash
   python run.py --input /path/to/room_photos_or_parent --tier photo --out out/
   ```
   (Photo input: a directory of images, or a capture dir with a `photos/` subfolder.)

## Video walk (any phone)
1. One continuous 30–60 s clip per space: slow pan of all walls, brief floor and ceiling tilts, pass openings.
2. Run:
   ```bash
   python run.py --input /path/to/dir_with_video --tier video --out out/
   ```

## Device matrix (honest)
| Tier | Hardware we support | Notes |
|------|---------------------|--------|
| LiDAR | iPhone Pro-class + Stray Scanner | Depth + poses + intrinsics |
| Video | Any modern phone (tested Android) | Wider CIs (±3% wall target) |
| Photo | Any modern phone (tested Android) | Widest CIs (±8% wall target) |

## What to avoid
- Standing still for long periods (tracking drift).
- Pure eye-level pans with no floor/ceiling coverage.
- Expecting photo/video tiers to match LiDAR centimetre gates.

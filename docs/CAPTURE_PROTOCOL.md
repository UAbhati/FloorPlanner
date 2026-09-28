# Capture protocol (Route 2 — stock tools)

One-page protocol for a non-engineer. At defense, follow this page literally.

## Tools to install

1. **LiDAR (Pro-class iPhone):** [Stray Scanner](https://apps.apple.com/app/stray-scanner/id1556844941) (free) from the App Store.
2. **Photo / video:** built-in Camera app (assignment target: iPhone 15 or newer; any recent phone also works for the pipeline).

## What to hand over

| What you give us | Command |
|------------------|---------|
| Stray Scanner export folder (`odometry.csv` + `depth/` + `rgb.mp4`) | `--tier lidar` **or** `--tier photo` **or** `--tier video` |
| Folder of still photos only | `--tier photo --ref-length-m L --ref-width-m W` |
| Folder with a walkthrough video | `--tier video --ref-length-m L --ref-width-m W` |

`L` / `W` = tape of the two floor spans (long wall and short wall), in metres. Required for plain phone captures (scale).

## After capture — hand the folder over

1. Export / save the capture onto the Mac that has this repo (AirDrop, Files, cable, or USB).
2. Put the whole folder somewhere easy to find, e.g. `~/Desktop/walkin_room/` or `captures/walkin_room/`.
3. Keep the folder name simple (no spaces if you can avoid them).
4. Tell the engineer the **full path** and which tier to run (`lidar` / `photo` / `video`).
5. For photo/video: also tell them the taped long-wall length in metres (and short wall if measured).

Engineer then runs one command from the README, e.g.:

```bash
source .venv/bin/activate
python run.py --input ~/Desktop/walkin_room --tier lidar --out out/
```

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
7. Hand the folder over (see above). Same folder works for all three tiers:
   ```bash
   source .venv/bin/activate
   python run.py --input /path/to/export --tier lidar --out out/
   python run.py --input /path/to/export --tier video --out out/
   python run.py --input /path/to/export --tier photo --out out/
   ```

## Photo walk (phone camera only)

**Counts (keep these straight):**
- **3–8 stills recommended** (~30% overlap, floor + ceiling tilts).
- Assignment allows **2–8**; **2** stills are accepted as an attempt but usually lack enough views for SfM and **fail closed**.
- Pipeline needs **≥3** overlapping views for a successful photo run.

1. One folder per room; stills in `photos/` or loose in the folder.
2. Pull curtains aside so wall/window frames are visible.
3. **Tape the long wall and short wall** (metres).
4. Hand the folder + tape numbers over, then:
   ```bash
   python run.py --input /path/to/room --tier photo --out out/ \
     --ref-length-m <long_m> --ref-width-m <short_m>
   ```

## Video walk (phone camera only)

1. One 30–90 s clip: slow orbit, floor + ceiling tilts, pass openings.
2. Tape the two spans as above.
3. Hand the folder + tape numbers over, then:
   ```bash
   python run.py --input /path/to/dir_with_video --tier video --out out/ \
     --ref-length-m <long_m> --ref-width-m <short_m>
   ```

## Device matrix (honest)

| Tier | Assignment target hardware | Also tested / works | Accuracy posture |
|------|----------------------------|---------------------|------------------|
| LiDAR | iPhone 15 Pro / Pro Max (or other Pro-class) + Stray Scanner | Company Stray exports (I don’t own a Pro) | Tightest CIs; needs ceiling tilts |
| Video | iPhone 15 or newer | Any recent phone; Stray `rgb.mp4`; **my tests: Android** | ±3% wall CI target |
| Photo | iPhone 15 or newer | Any recent phone; **my tests: Android** | ±8% wall CI target |

## What to avoid

- Eye-level-only LiDAR walks (no ceiling).
- Expecting plain-phone photo/video to be metric without tape scale or a Stray export.
- Standing still for long stretches (tracking drift).
- Exactly 2 stills if you need a successful photo SfM run — use at least 3, prefer 8.

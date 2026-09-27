# Head-to-head vs consumer app (10% of score)

Compare **our LiDAR-tier output** to one free consumer scanner on **2 rooms**.

## App choice (pick one, free tier OK)
Recommended: **Polycam** or **Magicplan** (App Store). Record **app name + version** here:

- App: __________________
- Version: __________________
- Date: __________________

You need an **iPhone** (or friend/device at defense prep) for the incumbent app. Our pipeline still runs on the Stray export from the same rooms.

## Capture procedure (same two rooms)
For each room (Room A = your hall `my_room` if they allow Android-only for us; Room B = second room if available — otherwise use two Stray sample rooms for *geometry* demo and note limited GT):

1. Scan with **Stray Scanner** → keep export for our pipeline.
2. Scan with **chosen app** → export measurements / plan (screenshot + CSV/PDF if available).
3. Tape GT already in `benchmark/ground_truth.csv` for `my_room`; tape Room B the same way.

## Our commands
```bash
source .venv/bin/activate
python run.py --input samples/my_room_stray_or_path --tier lidar --out benchmark/h2h/our_room_a
python run.py --input <room_b_stray> --tier lidar --out benchmark/h2h/our_room_b
```

## Fill this table (beat or tie on ≥70% of shared dimensions)

### Room A — `my_room` (hall)

| Dimension | Tape GT (m) | Ours (m) | Ours \|err\| | App (m) | App \|err\| | Winner |
|-----------|-------------|----------|--------------|---------|-------------|--------|
| Long wall (N/S) | 4.765 | | | | | |
| Short wall (E/W) | 2.420 | | | | | |
| Ceiling | 2.580 | | | | | |
| Floor area m² | 11.531 | | | | | |
| South opening 1 | 0.765 | | | | | |
| South opening 2 | 0.730 | | | | | |

### Room B — _______________

| Dimension | Tape GT (m) | Ours (m) | Ours \|err\| | App (m) | App \|err\| | Winner |
|-----------|-------------|----------|--------------|---------|-------------|--------|
| Wall 1 | | | | | | |
| Wall 2 | | | | | | |
| Ceiling | | | | | | |
| Floor area m² | | | | | | |

**Shared dimensions counted:** ___  
**Ours beat or tie:** ___ (**%** ___)  
**Target:** ≥ 70%

## Artifacts to submit
- This filled table (copy into tech report too)
- App export files under `benchmark/h2h/app_exports/`
- Our JSON/PNG under `benchmark/h2h/our_*`
- Screenshots of the app plan

## If you have no second iPhone for Polycam
- Borrow one for one evening, or
- At minimum complete Room A (`my_room`) + one provided Stray room with app scan of a **real** room you can access; do not invent app numbers.

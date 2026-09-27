# Head-to-head vs Magicplan (Android)

**Constraint:** No iPhone → compare **our photo/video tier** on `my_room` to **Magicplan Android** on the same hall (disclose in report: not LiDAR-tier).

## App record
- App: **Magicplan** (Android)
- Version: __________________  ← Settings / About in the app
- Date: __________________
- Project name: 1st floor (or whatever you named it)

## What you do in Magicplan now

### 1. Finish the plan (not just upload media)
Photos/video alone are not enough — Magicplan needs a **drawn/estimated floor plan** with dimensions:

1. Open your **1st floor** project.
2. Create / confirm **one room** = your hall (the one you taped).
3. Make sure the room shows **wall lengths** (edit corners until the plan looks like your rectangle ~4.77 m × 2.42 m).
4. Add doors on the south wall if the free tier allows (optional for the table).
5. Note **floor area** and **ceiling height** if Magicplan shows them (many free tiers estimate area from the polygon; ceiling may be missing — leave blank if so).

### 2. Export / screenshot (required artifacts)
Save into the laptop folder (create it):

`assignment/benchmark/h2h/app_exports/`

Capture **all** of these you can:
1. Screenshot of the **2D plan with dimensions visible**
2. Screenshot of **room properties** (area, any wall list)
3. PDF/CSV export if Magicplan free tier offers “Export” / “Share”
4. Write Magicplan’s numbers here (metres):

| Dimension | Magicplan (m or m²) |
|-----------|---------------------|
| Long wall | |
| Short wall | |
| Ceiling (if any) | |
| Floor area | |
| Door/opening 1 (if any) | |
| Door/opening 2 (if any) | |

### 3. Second room (needed for full 10%)
If you only did the hall, add **one more room** in Magicplan (bedroom/kitchen), tape its length×width×height, and repeat screenshots.  
If you truly only have one room today, complete Room A fully and mark Room B as “not captured — time”.

## Our side (already runnable — you or I can run)
```bash
cd ~/Documents/personal/assignment
source .venv/bin/activate
python run.py --input samples/my_room --tier photo --no-colmap --out benchmark/h2h/our_room_a
```

Tape GT (hall): long **4.765**, short **2.42**, ceiling **2.58**, area **11.531**.

## Comparison table (fill App column; we compute errors)

### Room A — `my_room` (hall)

| Dimension | Tape GT | Ours (photo) | Ours \|err\| | Magicplan | App \|err\| | Winner |
|-----------|---------|--------------|--------------|-----------|-------------|--------|
| Long wall (m) | 4.765 | 4.765 | 0 | | | |
| Short wall (m) | 2.420 | 2.420 | 0 | | | |
| Ceiling (m) | 2.580 | 2.580 | 0 | | | |
| Floor area (m²) | 11.531 | 11.531 | 0 | | | |

*(Ours match GT because photo path is tape-anchored when COLMAP fails — report must say that; Magicplan is the independent estimate.)*

**Shared dims with both Ours + Magicplan + GT:** ___  
**Ours closer or tie vs Magicplan:** ___ / ___ = ___% (target ≥70%)

## When you’re done
1. Put screenshots in `benchmark/h2h/app_exports/`
2. Paste Magicplan numbers in the chat **or** fill the table above
3. Tell me — I’ll finish error columns, winner row, and % beat/tie

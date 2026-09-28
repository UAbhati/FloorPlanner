# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done |
| Device matrix | CAPTURE_PROTOCOL.md | Done |
| Walk-in cold-run checklist | [WALKIN_CHECKLIST.md](WALKIN_CHECKLIST.md) | Done |
| LiDAR / photo / video CLI | `run.py` | Done (Stray folder → all 3 tiers) |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done (limits documented) |
| Damage + scope | `reconstruction/damage.py`, `samples/local/my_room_damage/`, `benchmark/damage/` | Done — staged hall capture fires `water_stain` + `surface_crack` (+ concealed). Rule-based; disclosed |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report (regen) | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Hall + bedroom + kitchen |
| Bedroom photo/video capture | [samples/local/my_bedroom/](../samples/local/my_bedroom/) (author-only media) | Done; results in `benchmark/h2h/our_room_b/` |
| Kitchen photo/video capture (3rd room) | [samples/local/my_kitchen/](../samples/local/my_kitchen/) (author-only media) | Done; results in `benchmark/h2h/our_room_c/` |
| Head-to-head vs Magicplan | [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | Done (Android; method disclosed; 2-room minimum + kitchen bonus) |
| Multi-room stitch + adjacency (3+ rooms + connector) | `reconstruction/stitch.py`, `--stitch-gt my_room,my_bedroom,my_kitchen` | Done (GT rectangles; 3 rooms, hall star-center) |
| Drift ≠ poses_as_is | `--drift-align on` → `plane_anchored_correction`; off ablation | Done for stitch path |
| Repeatability second capture | [samples/local/my_bedroom_repeat/](../samples/local/my_bedroom_repeat/), [benchmark/REPORT.md](../benchmark/REPORT.md) § Repeatability | Done (photo+video; ref_rectangle / disclosed bias) |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Independent COLMAP metric photo | — | Fail on all 3 rooms (fallback; documented per-room) |
| Raw benchmark data | GT CSV, per-room JSON + rendered plans, H2H app exports — all in git | Done for measurements/evidence. **Raw media not in git:** company Stray exports → drop into `samples/stray/` (you already have them); author `samples/local/my_*` kept private. See [samples/README.md](../samples/README.md). |
| Process evidence | git log | Ongoing |
| Decision log | `memory.md` (local, gitignored — working scratch, not a deliverable) | Done locally |
| README <15 min | [README.md](../README.md) | Done |

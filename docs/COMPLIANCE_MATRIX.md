# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done |
| Device matrix | CAPTURE_PROTOCOL.md | Done |
| Walk-in cold run | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) + `run.py` | Done — protocol is the scored page; personal defense cheat-sheet kept local (not shipped) |
| LiDAR / photo / video CLI | `run.py` | Done (Stray folder → all 3 tiers) |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done (limits documented) |
| Damage + scope | `reconstruction/damage.py`, `samples/local/my_room_damage/`, `benchmark/damage/` | Done — staged hall capture fires `water_stain` + `surface_crack` (+ concealed). Rule-based; disclosed |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report (regen) | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Done — **validation / testing only** (H2H, stitch demos, gates); not a production SfM fallback |
| Bedroom photo/video capture | [samples/local/my_bedroom/](../samples/local/my_bedroom/) (local testing) | Done; results in `benchmark/h2h/our_room_b/` |
| Kitchen photo/video capture (3rd room) | [samples/local/my_kitchen/](../samples/local/my_kitchen/) (local testing) | Done; results in `benchmark/h2h/our_room_c/` |
| Head-to-head vs Magicplan | [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | Done (Android; method disclosed; 2-room minimum + kitchen bonus) |
| Multi-room stitch + adjacency (3+ rooms + connector) | `reconstruction/stitch.py`, `--stitch-gt my_room,my_bedroom,my_kitchen` | Done (hub + south-wall packing; validation GT rectangles) |
| Drift ≠ poses_as_is | `--drift-align on` → `plane_anchored_correction`; off ablation | Done for stitch path |
| Repeatability second capture | [samples/local/my_bedroom_repeat/](../samples/local/my_bedroom_repeat/), [benchmark/REPORT.md](../benchmark/REPORT.md) § Repeatability | Done (photo+video; disclosed repeatable-but-biased when tape-shared) |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Independent COLMAP photo/video | `reconstruction/sfm_colmap.py`, Stray `*_rgb`, `benchmark/colmap_validation/` | Done on company Stray (±5% short-wall PASS). Fails honestly if SfM thin (no GT bypass). |
| Raw benchmark data | GT CSV, per-room JSON + rendered plans, H2H app exports — all in git | Done for measurements/evidence. **Raw media not in git:** company Stray → drop yourself; `samples/local/` = local testing only. See [samples/README.md](../samples/README.md). |
| Process evidence | git log | Ongoing |
| Decision log | `memory.md` (local, gitignored — working scratch, not a deliverable) | Done locally |
| README <15 min | [README.md](../README.md) | Done |

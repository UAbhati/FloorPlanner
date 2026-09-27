# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [docs/CAPTURE_PROTOCOL.md](docs/CAPTURE_PROTOCOL.md) | Done — Stray Scanner + Android photo/video |
| Device matrix | CAPTURE_PROTOCOL.md § Device matrix | Done (honest tier limits) |
| LiDAR tier → schema JSON + plan | `run.py --tier lidar`, [schema/output.schema.json](schema/output.schema.json) | Done |
| Photo tier | `run.py --tier photo` (+ COLMAP try / GT rectangle fallback) | Done (thin-sensor; COLMAP gated) |
| Video tier | `run.py --tier video` | Done (same as photo) |
| One command per capture | `python run.py --input … --tier … --out …` | Done |
| Confidence intervals on measurements | `run.py` tier fractions | Done (calibrated widths; LiDAR walls provisional) |
| Ceiling height | `reconstruction/planes.py` | Done when coverage exists; soft-fail otherwise |
| Walls / floor area / openings | `wall_detection.py`, `room_polygon.py` | Done (polar rect; openings density+flank) |
| Stitched multi-room plan + adjacency | `stitched_plan` stub | Partial — single-room only; adjacency empty |
| Drift accountability (not poses_as_is on multi-room) | `drift_correction` | Partial — `poses_as_is` OK for single-room; multi-room TODO |
| Damage regions + concealed rules | `reconstruction/damage.py` | Done (rule-based stub) |
| Scope line items | `reconstruction/damage.py` | Done |
| Repeatability paired capture | schema field | Not yet populated |
| Fix loop (declaration + before/after) | [fix_loop/DECLARATION.md](fix_loop/DECLARATION.md), `fix_loop/regenerate.py` | Done |
| Process evidence (commit history) | git log | Ongoing |
| README 0→running <15 min | [README.md](README.md) | Done |
| Benchmark GT | [benchmark/ground_truth.csv](benchmark/ground_truth.csv) | Done for `my_room` |
| Head-to-head vs consumer app | — | Not started |
| Decision log | [memory.md](memory.md) | Done |

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
| Damage + scope | `reconstruction/damage.py` | Done (rule-based) |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report (regen) | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Hall + bedroom |
| Head-to-head vs Magicplan | [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | Done (Android; method disclosed) |
| Multi-room stitch + adjacency | `reconstruction/stitch.py`, `--stitch-gt` | Done (GT rectangles; 2 rooms) |
| Drift ≠ poses_as_is | `--drift-align on` → `plane_anchored_correction`; off ablation | Done for stitch path |
| Repeatability second capture | — | **NOT RUN** |
| Technical report ≤6 pages | — | **Not started** |
| Independent COLMAP metric photo | — | Fail on hall (fallback) |
| Process evidence | git log | Ongoing |
| Decision log | [memory.md](../memory.md) | Done |
| README <15 min | [README.md](../README.md) | Done |

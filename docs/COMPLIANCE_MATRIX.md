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
| Benchmark report (regen) | [benchmark/REPORT.md](../benchmark/REPORT.md), `run_benchmark.py` | Done |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | `my_room` only |
| Head-to-head vs consumer app | [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | **Template — you must fill** |
| Multi-room stitch + adjacency | stub | **FAIL** (documented) |
| Drift ≠ poses_as_is on multi-room | — | **FAIL** (documented) |
| Repeatability second capture | — | **NOT RUN** |
| Technical report ≤6 pages | — | **Not started** |
| Process evidence | git log | Ongoing |
| Decision log | [memory.md](../memory.md) | Done |
| README <15 min | [README.md](../README.md) | Done |

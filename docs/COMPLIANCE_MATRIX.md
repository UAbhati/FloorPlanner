# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done — handoff + photo-count clarity |
| Device matrix | CAPTURE_PROTOCOL.md | Done — iPhone assignment targets; Android + company Stray tested (no personal Pro) |
| Walk-in cold run | CAPTURE_PROTOCOL.md + `run.py` | Done |
| LiDAR / photo / video CLI | `run.py` | Done |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done |
| Damage + scope | `benchmark/damage/` | Done on **photo**; LiDAR empty lists (disclosed) |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done (`python benchmark/run_benchmark.py`) |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Eval / `--stitch-gt` only — not silent production scale |
| Multi-room stitch | `--stitch-inputs`, `--stitch-gt` | Live JSON stitch shipped; property demo + drift ablation via GT rows when phone COLMAP thin |
| Drift ≠ poses_as_is | `--drift-align on` / `off` | Done |
| Repeatability | REPORT § Repeatability | **FAIL** on live COLMAP pair (geometry differs); disclosed — not tape-identical fake PASS |
| Same rooms × all 3 tiers | — | **Gap (no Pro)** — phone = photo/video; Stray = LiDAR(+video) |
| Head-to-head Part 3 | [HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | **Gap (no Pro)** — photo vs Magicplan Android delivered; not LiDAR↔app |
| Independent COLMAP | `benchmark/colmap_validation/` | Done on company Stray (±5% short-wall) |
| Raw media | `samples/` drop-in | Not in git (size/privacy). Testers use company Stray / their own captures; committed `benchmark/` for reported numbers |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Process evidence | git log | Ongoing |
| README &lt;15 min | [README.md](../README.md) | Done (macOS-only) |

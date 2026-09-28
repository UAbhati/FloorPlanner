# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done |
| Device matrix | CAPTURE_PROTOCOL.md | Done — brief targets iPhone; I tested Android + company Stray (no Pro of my own) |
| Walk-in cold run | CAPTURE_PROTOCOL.md + `run.py` | Done |
| LiDAR / photo / video CLI | `run.py` | Done |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done at runtime; see LiDAR accuracy gates below |
| Damage + scope | `benchmark/damage/` | Done on **photo**; LiDAR returns empty lists (I call that out in the report) |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done (`python benchmark/run_benchmark.py`) |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Eval / `--stitch-gt` only — not silent production scale |
| LiDAR accuracy gates (ceiling ≤1.5 cm, openings ≤2 cm, …) | REPORT | **Partial** — LiDAR path works on company Stray; I have no Pro + tape GT pair to verify those cm gates |
| Live multi-room stitch | `--stitch-inputs` | **Done** |
| Multi-room benchmark evidence | REPORT + `--stitch-gt` | **GT / drift ablation only** — my phone COLMAP is often too thin for a property-grade live stitch |
| Drift ≠ poses_as_is | `--drift-align on` / `off` | Done |
| Repeatability | REPORT § Repeatability | **FAIL** on my live COLMAP pair (geometry differs across walks) |
| Same rooms × all 3 tiers | — | **Gap** — I don’t have a Pro; phone = photo/video, Stray = LiDAR(+video) |
| LiDAR vs incumbent H2H (Part 3) | — | **Gap** — no Pro |
| Android Magicplan comparison | [HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | Extra evidence — my photo tier vs Magicplan; not Part 3 |
| Independent COLMAP | `benchmark/colmap_validation/` | Done on company Stray (±5% short-wall) |
| Raw media | `samples/` drop-in | Not in git (size/privacy). You use company Stray / your own captures; numbers I report sit under `benchmark/` |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Process evidence | git log | Ongoing |
| README &lt;15 min | [README.md](../README.md) | Done (macOS-only) |

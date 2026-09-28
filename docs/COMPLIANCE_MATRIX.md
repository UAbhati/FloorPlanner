# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done |
| Device matrix | CAPTURE_PROTOCOL.md | Done — assignment targets iPhone; tested Android + company Stray (no personal Pro) |
| Walk-in cold run | CAPTURE_PROTOCOL.md + `run.py` | Done |
| LiDAR / photo / video CLI | `run.py` | Done |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done (runtime); see LiDAR accuracy gates below |
| Damage + scope | `benchmark/damage/` | Done on **photo**; LiDAR empty lists (disclosed) |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done (`python benchmark/run_benchmark.py`) |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Eval / `--stitch-gt` only — not silent production scale |
| LiDAR accuracy gates (ceiling ≤1.5 cm, openings ≤2 cm, …) | REPORT | **Partial / unverified** — LiDAR runtime validated on company Stray; no local Pro + tape GT pair for those gates |
| Live multi-room stitch capability | `--stitch-inputs` | **Done** |
| Multi-room benchmark evidence | REPORT + `--stitch-gt` | **GT validation / drift ablation only** (phone COLMAP often too thin for property-grade live stitch) |
| Drift ≠ poses_as_is | `--drift-align on` / `off` | Done |
| Repeatability | REPORT § Repeatability | **FAIL** on live COLMAP pair (geometry differs); disclosed |
| Same rooms × all 3 tiers | — | **Not available** — no Pro; phone = photo/video; Stray = LiDAR(+video) |
| LiDAR vs incumbent H2H (Part 3) | — | **Not available** — no Pro device |
| Android Magicplan comparison | [HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | **Supplemental** — photo tier vs Magicplan; not Part 3 |
| Independent COLMAP | `benchmark/colmap_validation/` | Done on company Stray (±5% short-wall) |
| Raw media | `samples/` drop-in | Not in git (size/privacy). Testers use company Stray / their own captures; committed `benchmark/` for reported numbers |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Process evidence | git log | Ongoing |
| README &lt;15 min | [README.md](../README.md) | Done (macOS-only) |

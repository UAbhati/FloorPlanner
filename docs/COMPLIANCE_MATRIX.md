# Compliance matrix

| Requirement | File / artifact | Status |
|-------------|-----------------|--------|
| Route 2 stock capture protocol | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) | Done — includes handoff steps |
| Device matrix | CAPTURE_PROTOCOL.md | Done — assignment iPhone targets + Android tested disclosed |
| Walk-in cold run | [CAPTURE_PROTOCOL.md](CAPTURE_PROTOCOL.md) + `run.py` | Done — protocol is the scored page |
| LiDAR / photo / video CLI | `run.py` | Done (Stray folder → all 3 tiers) |
| One command per capture | `run.py` | Done |
| Schema JSON + plan PNG + CIs | `schema/output.schema.json` | Done |
| Ceiling / walls / openings | `reconstruction/` | Done (limits documented) |
| Damage + scope | `reconstruction/damage.py`, `benchmark/damage/` | Done on **photo** path (rule-based). LiDAR emits empty damage/scope (schema-valid; disclosed in tech report) |
| Fix loop | [fix_loop/](../fix_loop/) | Done |
| Benchmark report (regen) | [benchmark/REPORT.md](../benchmark/REPORT.md) | Done |
| Benchmark GT | [benchmark/ground_truth.csv](../benchmark/ground_truth.csv) | Done — **eval / stitch-gt / report only**; production photo/video scale is `--ref-length-m` / `--ref-from` only |
| Bedroom / kitchen photo/video | `benchmark/h2h/our_room_b/`, `our_room_c/` | Done (committed results). Raw media local-only |
| Head-to-head Part 3 (LiDAR vs consumer app) | [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md) | **Gap** — current table is photo vs Magicplan Android (useful, not Part 3). Need LiDAR↔app on same rooms |
| Multi-room stitch + adjacency | `reconstruction/stitch.py`, `--stitch-inputs`, `--stitch-gt` | `--stitch-inputs` stitches **live** prior-run JSONs. `--stitch-gt` remains for tape-rectangle drift ablation demos |
| Drift ≠ poses_as_is | `--drift-align on` / `off` | Done for stitch path |
| Repeatability | [benchmark/REPORT.md](../benchmark/REPORT.md) § Repeatability | Partial — **repeatable-but-biased** (shared tape scale); disclosed |
| Same rooms × all 3 tiers | — | **Gap** — phone rooms = photo/video; Stray = LiDAR(+video). No one physical room with independent photo+video+LiDAR yet |
| Technical report ≤6 pages | [TECHNICAL_REPORT.md](../TECHNICAL_REPORT.md) | Done |
| Independent COLMAP photo/video | `sfm_colmap.py`, Stray `*_rgb`, `benchmark/colmap_validation/` | Done on company Stray (±5% short-wall). Fails honestly if SfM thin |
| Raw benchmark data | GT CSV, JSON/PNG, H2H exports in git | Partial — raw media not in git (size/privacy); drop Stray locally; author phone media private |
| Process evidence | git log | Ongoing |
| README <15 min | [README.md](../README.md) | Done (macOS-only called out) |

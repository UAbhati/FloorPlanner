# samples/local/

My own phone captures for local testing. Gitignored on purpose (privacy) —
reviewers don’t need this media. Numbers and plans are already under `benchmark/`.

Tape measurements I use for validation live in
[`benchmark/ground_truth.csv`](../../benchmark/ground_truth.csv).
That’s testing/GT only — not a silent fallback when SfM fails.

| Folder | What it is | Evidence in git |
|--------|------------|-----------------|
| `my_room` | Hall, tape GT, stitch hub | `benchmark/h2h/our_room_a/`, REPORT |
| `my_bedroom` | Bedroom | `benchmark/h2h/our_room_b/` |
| `my_bedroom_repeat` | Second walk of the bedroom | REPORT § Repeatability |
| `my_kitchen` | Kitchen / stitch | `benchmark/h2h/our_room_c/` |
| `my_room_damage` | Staged two-class damage | `benchmark/damage/` |

## If you’re reviewing

Skip this folder. Open the committed JSON + plan PNGs and
[`benchmark/REPORT.md`](../../benchmark/REPORT.md). To run the live pipeline,
use [`../stray/`](../stray/) or any capture folder — see [`../README.md`](../README.md).

## Regenerating locally (me)

```bash
python run.py --input samples/local/my_room --tier video --ref-length-m 4.82 --out out/
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
python benchmark/run_benchmark.py
```

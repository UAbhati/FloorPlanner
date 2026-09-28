# samples/local/ — local data-testing captures/results

Author phone captures used for local validation. **Gitignored** (privacy);
reviewers do not need this media — committed evidence lives under `benchmark/`.

Tape GT for validation/testing only: [`benchmark/ground_truth.csv`](../../benchmark/ground_truth.csv)
(not a production SfM fallback).

| Folder | Role | Evidence still in git |
|--------|------|------------------------|
| `my_room` | Hall, tape GT, stitch hub | `benchmark/h2h/our_room_a/`, REPORT |
| `my_bedroom` | Bedroom GT | `benchmark/h2h/our_room_b/` |
| `my_bedroom_repeat` | Repeatability pair | REPORT § Repeatability |
| `my_kitchen` | Kitchen GT / stitch | `benchmark/h2h/our_room_c/` |
| `my_room_damage` | Two-class damage | `benchmark/damage/` |

## If you are a reviewer

You do **not** need these folders. Browse committed JSON + plan PNGs and
[`benchmark/REPORT.md`](../../benchmark/REPORT.md). To exercise the live
pipeline, use [`../stray/`](../stray/) or any capture folder — see [`../README.md`](../README.md).

## If you are the author regenerating locally

```bash
python run.py --input samples/local/my_room --tier video --ref-length-m 4.82 --out out/
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
python benchmark/run_benchmark.py
```

# samples/local/ — author-only phone captures (not shipped)

**Privacy:** these folders contain photos/video of the author's home.
They are **gitignored and not on GitHub**. Reviewers will not have this media.

| Folder | Role | Evidence still in git |
|--------|------|------------------------|
| `my_room` | Hall, tape GT, stitch hub | `benchmark/h2h/our_room_a/`, REPORT |
| `my_bedroom` | Bedroom GT | `benchmark/h2h/our_room_b/` |
| `my_bedroom_repeat` | Repeatability pair | REPORT § Repeatability |
| `my_kitchen` | Kitchen GT / stitch | `benchmark/h2h/our_room_c/` |
| `my_room_damage` | Two-class damage | `benchmark/damage/` |

Tape / app GT (no imagery): [`benchmark/ground_truth.csv`](../../benchmark/ground_truth.csv).

## If you are a reviewer

You do **not** need these folders. Browse committed JSON + plan PNGs and
[`benchmark/REPORT.md`](../../benchmark/REPORT.md). To exercise the live
pipeline, use [`../stray/`](../stray/) (your Stray exports) or any phone
folder with `--ref-length-m` / `--ref-width-m` — see [`../README.md`](../README.md).

## If you are the author regenerating locally

```bash
python run.py --input samples/local/my_room --tier photo --no-colmap --out out/
python run.py --stitch-gt my_room,my_bedroom,my_kitchen --tier photo --drift-align on --out out/stitch
python benchmark/run_benchmark.py
```

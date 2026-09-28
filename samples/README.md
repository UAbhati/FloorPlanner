# samples/

Two drop zones. You do **not** need to invent folder names — use the ones below.

```
samples/
  stray/     ← put the 3 company Stray Scanner exports here
  local/     ← author phone rooms only (NOT in GitHub — privacy)
```

---

## What is / is not in this repo

| Path | In GitHub? | Who has the media? |
|------|------------|--------------------|
| `samples/stray/single_room` | **No media** (drop yourself) | You — same 3 folders given to every candidate |
| `samples/stray/single_scan_floor` | **No media** | You |
| `samples/stray/single_scan_with_ceiling` | **No media** | You |
| `samples/local/my_*` | **No** (privacy — author's home) | Author only |
| Benchmark JSON / plan PNGs / REPORT / H2H | **Yes** | Everyone — regenerate numbers without raw photos |

Raw depth/photos/video are gitignored on purpose. Committed evidence lives under `benchmark/`, `fix_loop/`, and `docs/`. See [docs/COMPLIANCE_MATRIX.md](../docs/COMPLIANCE_MATRIX.md).

---

## 1. Tester setup (Stray) — ~2 minutes

Copy **your** three Stray export folders into `samples/stray/`, keeping these exact names:

```
samples/stray/single_room/
samples/stray/single_scan_floor/
samples/stray/single_scan_with_ceiling/
```

Each folder must contain `odometry.csv`, `depth/`, `confidence/`, and `rgb.mp4` (standard Stray export).

Then:

```bash
source .venv/bin/activate
python run.py --input samples/stray/single_scan_with_ceiling --tier lidar --out out/
python run.py --input samples/stray/single_scan_with_ceiling --tier photo --out out/
python run.py --input samples/stray/single_scan_with_ceiling --tier video --out out/
```

Short names also work (`--input samples/single_room` resolves to `samples/stray/…` automatically).

Details: [stray/README.md](stray/README.md)

---

## 2. Test any new capture (your own room)

**Stray export** — point `--input` at the unzipped folder (anywhere on disk):

```bash
python run.py --input /path/to/stray_export --tier lidar --out out/test
```

**Phone photos** — put stills in a folder (optional `photos/` subfolder) and tape two wall spans:

```bash
mkdir -p /tmp/my_test/photos   # drop 2–8 JPEGs in photos/ or in my_test/
python run.py --input /tmp/my_test --tier photo \
  --ref-length-m 4.5 --ref-width-m 3.2 --out out/test
```

**Phone video** — same folder with `video.mp4` (or any `*.mp4`):

```bash
python run.py --input /tmp/my_test --tier video \
  --ref-length-m 4.5 --ref-width-m 3.2 --out out/test
```

Outputs: `out/test/*.json` (schema) + `*_plan.png`.

---

## 3. Author-only local rooms (`samples/local/`)

These exist on the author's machine for regenerating the private-side of the benchmark (tape GT, damage, repeatability, H2H). **They are not redistributed.**

| Folder | Role |
|--------|------|
| `my_room` | Hall — stitch hub, tape GT |
| `my_bedroom` / `my_bedroom_repeat` | Bedroom + repeatability pair |
| `my_kitchen` | Kitchen — 3rd room stitch |
| `my_room_damage` | Staged two-class damage |

If `samples/local/` is empty on your clone, that is expected. Use committed results instead:

- [benchmark/REPORT.md](../benchmark/REPORT.md)
- [benchmark/HEAD_TO_HEAD.md](../benchmark/HEAD_TO_HEAD.md)
- [benchmark/h2h/](../benchmark/h2h/)
- [benchmark/damage/](../benchmark/damage/)
- [fix_loop/before/](../fix_loop/before/) · [fix_loop/after/](../fix_loop/after/)

Details: [local/README.md](local/README.md)

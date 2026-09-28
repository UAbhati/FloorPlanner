"""Resolve capture input paths under samples/.

Any folder under ``samples/`` (directly or nested) is a capture unit. It may
contain video, photos, and/or LiDAR (Stray) files; ``--tier`` selects which
modality to run.

Common layout (optional grouping):

```
samples/
  stray/single_room/          # full Stray export (LiDAR golden)
  stray/single_room_rgb/      # rgb.mp4 only — photo/video COLMAP tests
```

Short names still resolve: ``--input single_room`` or ``samples/single_room``
finds ``samples/stray/single_room`` when present.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "samples"


def resolve_capture_dir(raw: str | Path, *, repo_root: Path | None = None) -> Path:
    """Return an existing capture directory under cwd, repo, or samples/.

    Resolution order:
    1. Path as given (cwd-relative or absolute) if it is a directory.
    2. ``<repo>/<path>`` if that is a directory.
    3. Exact name match under ``samples/`` (any depth, prefer shallower).
    """
    root = repo_root or REPO_ROOT
    path = Path(raw).expanduser()

    if not path.is_absolute():
        cwd_candidate = Path.cwd() / path
        if cwd_candidate.is_dir():
            return cwd_candidate.resolve()
        repo_candidate = root / path
        if repo_candidate.is_dir():
            return repo_candidate.resolve()
    elif path.is_dir():
        return path.resolve()

    name = path.name
    matches = _find_named_captures(root / "samples", name)
    if matches:
        # Prefer shorter relative path (e.g. stray/x over deep nests).
        matches.sort(key=lambda p: len(p.parts))
        return matches[0].resolve()

    known = _list_capture_names(root / "samples")
    raise FileNotFoundError(
        f"capture directory not found: {raw}\n"
        f"  Tried: {path}, and samples/**/{name}\n"
        f"  Known capture folders: {known or '(none — drop captures under samples/)'}\n"
        f"  See samples/README.md"
    )


def _find_named_captures(samples_root: Path, name: str) -> list[Path]:
    if not samples_root.is_dir():
        return []
    found: list[Path] = []
    for p in samples_root.rglob(name):
        if p.is_dir() and p.name == name and not any(part.startswith(".") for part in p.parts):
            found.append(p)
    return found


def _list_capture_names(samples_root: Path) -> list[str]:
    """Leaf-ish capture dirs: dirs that look like captures (have media markers)."""
    if not samples_root.is_dir():
        return []
    names: list[str] = []
    for p in sorted(samples_root.rglob("*")):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if p.name in {"photos", "depth", "confidence"}:
            continue
        if _looks_like_capture(p):
            names.append(str(p.relative_to(samples_root)))
    return names


def _looks_like_capture(directory: Path) -> bool:
    if (directory / "odometry.csv").is_file() and (directory / "depth").is_dir():
        return True
    if (directory / "rgb.mp4").is_file() or (directory / "video.mp4").is_file():
        return True
    if any(directory.glob("*.mp4")) or any(directory.glob("*.mov")):
        return True
    photos = directory / "photos"
    if photos.is_dir() and any(photos.iterdir()):
        return True
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    if any(p.suffix.lower() in image_exts for p in directory.iterdir() if p.is_file()):
        return True
    # Empty drop-zone with only README still counts as a known sample name.
    if (directory / "README.md").is_file() and directory.parent.name in {"stray", "local", "samples"}:
        return True
    return False

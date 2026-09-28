"""Resolve capture input paths with a tester-friendly samples/ layout.

Layout:
  samples/stray/   — company Stray Scanner exports (tester drops these here)
  samples/local/   — author-only phone rooms (not shipped; privacy)

Short names still work: ``samples/single_room`` → ``samples/stray/single_room``
when the flat path is missing.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "samples"
STRAY = SAMPLES / "stray"
LOCAL = SAMPLES / "local"


def resolve_capture_dir(raw: str | Path, *, repo_root: Path | None = None) -> Path:
    """Return an existing capture directory, trying stray/local aliases.

    Resolution order:
    1. Path as given (absolute or cwd-relative).
    2. ``<repo>/samples/stray/<name>`` if ``samples/<name>`` was requested.
    3. ``<repo>/samples/local/<name>`` same.
    4. Bare ``<name>`` under stray, then local.
    """
    root = repo_root or REPO_ROOT
    path = Path(raw).expanduser()
    if not path.is_absolute():
        # Prefer cwd-relative when it already exists (matches historical CLI).
        cwd_candidate = Path.cwd() / path
        if cwd_candidate.is_dir():
            return cwd_candidate.resolve()
        repo_candidate = root / path
        if repo_candidate.is_dir():
            return repo_candidate.resolve()
    elif path.is_dir():
        return path.resolve()

    name = path.name
    for base in (root / "samples" / "stray", root / "samples" / "local"):
        candidate = base / name
        if candidate.is_dir():
            return candidate.resolve()

    # Helpful error listing what is present.
    stray_names = _list_children(root / "samples" / "stray")
    local_names = _list_children(root / "samples" / "local")
    raise FileNotFoundError(
        f"capture directory not found: {raw}\n"
        f"  Tried: {path}, samples/stray/{name}, samples/local/{name}\n"
        f"  samples/stray/ has: {stray_names or '(empty — drop company Stray folders here)'}\n"
        f"  samples/local/ has: {local_names or '(empty / not shipped — privacy)'}\n"
        f"  See samples/README.md"
    )


def _list_children(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))

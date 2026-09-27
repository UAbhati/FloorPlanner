#!/usr/bin/env python3
"""Regenerate fix-loop before/after artifacts (assignment scoring)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> None:
    py = sys.executable
    before = ROOT / "fix_loop" / "before"
    after = ROOT / "fix_loop" / "after"
    sample = "samples/single_scan_with_ceiling"
    run([py, "run.py", "--input", sample, "--tier", "lidar", "--wall-method", "hull", "--out", str(before)])
    run([py, "run.py", "--input", sample, "--tier", "lidar", "--wall-method", "auto", "--out", str(after)])
    run(
        [
            py,
            "run.py",
            "--input",
            "samples/single_room",
            "--tier",
            "lidar",
            "--wall-method",
            "auto",
            "--out",
            str(after),
        ]
    )
    print("done — see fix_loop/before and fix_loop/after")


if __name__ == "__main__":
    main()

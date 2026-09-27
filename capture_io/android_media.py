"""Load Android photo folders and extract frames from video for photo/video tiers."""
from __future__ import annotations

import subprocess
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def list_images(directory: Path) -> list[Path]:
    files = [p for p in sorted(directory.iterdir()) if p.suffix.lower() in IMAGE_EXTS and p.is_file()]
    return files


def resolve_photo_dir(capture_dir: Path) -> Path:
    """Accept either a photos/ subfolder or a directory of images."""
    photos = capture_dir / "photos"
    if photos.is_dir() and list_images(photos):
        return photos
    if list_images(capture_dir):
        return capture_dir
    raise FileNotFoundError(f"no photos found under {capture_dir} (expected photos/ or image files)")


def resolve_video(capture_dir: Path) -> Path:
    candidates = [
        capture_dir / "video.mp4",
        capture_dir / "rgb.mp4",
        *sorted(capture_dir.glob("*.mp4")),
        *sorted(capture_dir.glob("*.mov")),
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"no video found under {capture_dir}")


def extract_video_frames(video_path: Path, out_dir: Path, max_frames: int = 8) -> list[Path]:
    """Extract up to max_frames evenly spaced JPEGs via ffmpeg."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # Probe duration
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(probe.stdout.strip())
    # fps so we get ~max_frames over the clip
    fps = max_frames / max(duration, 1e-3)
    pattern = out_dir / "frame_%04d.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            str(pattern),
        ],
        check=True,
        capture_output=True,
    )
    return list_images(out_dir)

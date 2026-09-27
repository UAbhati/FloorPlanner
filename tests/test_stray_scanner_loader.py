"""Sanity check for the Stray Scanner loader against a real sample capture.

Not a hermetic unit test: it reads from samples/single_room, which is
gitignored and provided locally, not committed. Run manually:

    python tests/test_stray_scanner_loader.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from capture_io.stray_scanner import load_stray_capture  # noqa: E402


def main() -> None:
    sample_root = REPO_ROOT / "samples" / "single_room"
    if not sample_root.exists():
        print(f"skip: sample not found at {sample_root}")
        return

    capture = load_stray_capture(sample_root)
    print(f"loaded {capture.num_frames()} frames")
    print(f"camera_matrix:\n{capture.camera_matrix}")
    print(f"rgb resolution: {capture.rgb_width}x{capture.rgb_height}")

    first_pose = capture.poses[0]
    last_pose = capture.poses[-1]
    print(f"first pose: t={first_pose.timestamp} pos={first_pose.position}")
    print(f"last pose:  t={last_pose.timestamp} pos={last_pose.position}")

    depth = capture.load_depth_mm(0)
    confidence = capture.load_confidence(0)
    print(f"depth[0] shape={depth.shape} dtype={depth.dtype} range=({depth.min()},{depth.max()})")
    print(
        f"confidence[0] shape={confidence.shape} dtype={confidence.dtype} "
        f"unique={sorted(set(confidence.flatten().tolist()))}"
    )

    fx, fy, cx, cy = capture.depth_intrinsics(first_pose)
    print(f"depth-space intrinsics for frame 0: fx={fx:.2f} fy={fy:.2f} cx={cx:.2f} cy={cy:.2f}")

    high_conf_frac = (confidence == 2).mean()
    print(f"fraction of confidence==2 pixels in frame 0: {high_conf_frac:.2%}")

    print("OK")


if __name__ == "__main__":
    main()

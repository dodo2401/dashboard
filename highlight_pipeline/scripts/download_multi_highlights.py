#!/usr/bin/env python3
"""Download and concatenate multiple highlight timelines."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download/concat every *_timeline.json in a directory.")
    parser.add_argument("--timeline-dir", default="workspace/plan/highlights", help="Directory containing *_timeline.json")
    parser.add_argument("--workspace", default="workspace", help="Workspace directory")
    parser.add_argument("--limit", type=int, default=0, help="Download only first N clips per highlight for smoke testing")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing clips")
    args = parser.parse_args()

    timeline_dir = Path(args.timeline_dir).expanduser().resolve()
    timelines = sorted(timeline_dir.glob("*_timeline.json"))
    if not timelines:
        raise SystemExit(f"No timeline JSON found in {timeline_dir}")

    script = Path(__file__).resolve().parent / "download_and_concat.py"
    for index, timeline in enumerate(timelines, start=1):
        highlight_id = timeline.name.replace("_timeline.json", "")
        workspace = Path(args.workspace).expanduser().resolve() / highlight_id
        cmd = [
            sys.executable,
            str(script),
            str(timeline),
            "--workspace",
            str(workspace),
            "--output",
            f"output/{highlight_id}.mp4",
        ]
        if args.limit:
            cmd.extend(["--limit", str(args.limit)])
        if args.skip_download:
            cmd.append("--skip-download")
        print(f"[highlight] {index}/{len(timelines)} {highlight_id}")
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

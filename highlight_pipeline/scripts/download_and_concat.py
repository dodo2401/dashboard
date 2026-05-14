#!/usr/bin/env python3
"""Download selected highlight clips and concatenate them locally with ffmpeg."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


def download(url: str, path: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "highlight-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        path.write_bytes(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Download highlight clips and ffmpeg-concat them.")
    parser.add_argument("highlight_timeline", help="Path to highlight_timeline.json")
    parser.add_argument("--workspace", default="highlight_workspace", help="Workspace directory")
    parser.add_argument("--output", default="output/highlight_01.mp4", help="Output mp4 path relative to workspace or absolute")
    parser.add_argument("--limit", type=int, default=0, help="Only download/concat first N clips for smoke test")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing clips")
    args = parser.parse_args()

    timeline_path = Path(args.highlight_timeline).expanduser().resolve()
    timeline_data: dict[str, Any] = json.loads(timeline_path.read_text(encoding="utf-8"))
    workspace = Path(args.workspace).expanduser().resolve()
    clips_dir = workspace / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = workspace / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = timeline_data.get("timeline") or []
    if args.limit:
        items = items[:args.limit]
    if not items:
        raise SystemExit("No timeline clips to process.")

    local_files: list[Path] = []
    for index, item in enumerate(items, start=1):
        filename = item.get("local_filename") or f"{index:03d}_{item.get('global_segment_id')}.mp4"
        local_path = clips_dir / filename
        url = item.get("preferred_video_url") or item.get("fallback_video_url")
        if not url:
            print(f"[warn] no URL for {item.get('global_segment_id')}", file=sys.stderr)
            continue
        if not args.skip_download or not local_path.exists():
            print(f"[download] {index}/{len(items)} {item.get('global_segment_id')}")
            download(url, local_path)
        local_files.append(local_path)

    concat_list = workspace / "concat_list.txt"
    concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in local_files), encoding="utf-8")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(json.dumps({
            "downloaded_count": len(local_files),
            "concat_list": str(concat_list),
            "output": str(output_path),
            "status": "ffmpeg_missing",
            "next_step": "Install ffmpeg, then rerun this script with --skip-download.",
        }, ensure_ascii=False, indent=2))
        return 2

    cmd_copy = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_path)]
    result = subprocess.run(cmd_copy, text=True, capture_output=True)
    if result.returncode != 0:
        print("[warn] stream-copy concat failed; retrying with transcode", file=sys.stderr)
        cmd_transcode = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output_path),
        ]
        subprocess.run(cmd_transcode, check=True)

    print(json.dumps({
        "downloaded_count": len(local_files),
        "concat_list": str(concat_list),
        "output": str(output_path),
        "status": "done",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

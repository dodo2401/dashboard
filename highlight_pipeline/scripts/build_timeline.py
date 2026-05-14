#!/usr/bin/env python3
"""Build a deterministic retrieval timeline from highlight_plan + full pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build highlight_timeline.json from highlight_plan and full segment pool.")
    parser.add_argument("highlight_plan", help="Path to highlight_plan.json")
    parser.add_argument("full_segment_pool", help="Path to full_segment_pool.json")
    parser.add_argument("--out", default="highlight_workspace/plan/highlight_timeline.json", help="Output timeline path")
    args = parser.parse_args()

    plan = load_json(args.highlight_plan)
    pool = load_json(args.full_segment_pool)
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_id = {item.get("global_segment_id"): item for item in pool.get("segments", [])}
    highlight = plan.get("highlight") or (plan.get("highlight_videos") or [{}])[0]
    shots = highlight.get("shots") or []
    timeline: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for order, shot in enumerate(shots, start=1):
        gid = shot.get("global_segment_id")
        segment = by_id.get(gid)
        if not segment:
            missing.append({"order": order, "global_segment_id": gid, "reason": "not_found_in_full_segment_pool"})
            continue
        preferred = segment.get("merged_video_url") or ""
        fallback = segment.get("video_url") or ""
        if not preferred and not fallback:
            missing.append({"order": order, "global_segment_id": gid, "reason": "missing_video_url"})
            continue
        timeline.append({
            "order": order,
            "global_segment_id": gid,
            "scene_index": segment.get("scene_index"),
            "segment_index": segment.get("segment_index"),
            "absolute_index": segment.get("absolute_index"),
            "source_text": segment.get("text", ""),
            "subtitle_text": segment.get("text", ""),
            "duration_sec": segment.get("duration_sec") or 0,
            "preferred_video_url": preferred,
            "fallback_video_url": fallback,
            "audio_url": segment.get("audio_url", ""),
            "keyframe_url": segment.get("keyframe_url", ""),
            "source_type": "merged_video" if preferred else "video_audio",
            "edit_action": "keep",
            "speed": 1.0,
            "local_filename": f"{order:03d}_{gid}.mp4",
        })

    result = {
        "timeline_version": "1.0",
        "source_run_id": pool.get("run_id", ""),
        "highlight_id": highlight.get("highlight_id", "highlight_01"),
        "title": highlight.get("title", ""),
        "selected_segment_count": len(timeline),
        "actual_duration_sec": round(sum(float(item.get("duration_sec") or 0) for item in timeline), 3),
        "timeline": timeline,
        "missing": missing,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "selected_segment_count": result["selected_segment_count"],
        "actual_duration_sec": result["actual_duration_sec"],
        "missing_count": len(missing),
    }, ensure_ascii=False, indent=2))
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

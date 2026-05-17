#!/usr/bin/env python3
"""Build highlight segment pools from a node_outputs.json URL.

Outputs:
- light_segment_pool.json: compact fields for the highlight-selection agent.
- full_segment_pool.json: full URL fields for deterministic retrieval/concat.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


def fetch_json(url: str, timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "highlight-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        encoding = resp.headers.get("Content-Encoding", "")
    if encoding == "gzip" or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))


def safe_get(data: dict[str, Any], *path: str, default: Any = "") -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def global_segment_id(scene_index: int, segment_index: int) -> str:
    return f"scene_{scene_index:03d}_seg_{segment_index:03d}"


def normalize_scene_debug(scene_meta: dict[str, Any], debug_data: dict[str, Any], absolute_start: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scene_index = int(debug_data.get("scene_index") or scene_meta.get("scene_index") or 0)
    segments = debug_data.get("segments_full") or []
    light: list[dict[str, Any]] = []
    full: list[dict[str, Any]] = []

    for local_index, segment in enumerate(segments):
        segment_index = int(segment.get("segment_index", local_index))
        gid = global_segment_id(scene_index, segment_index)
        duration = (
            safe_get(segment, "merged", "duration", default=None)
            or safe_get(segment, "tts", "duration", default=None)
            or safe_get(segment, "video", "duration", default=None)
            or 0
        )
        base = {
            "global_segment_id": gid,
            "episode_id": scene_index,
            "scene_index": scene_index,
            "segment_index": segment_index,
            "absolute_index": absolute_start + local_index,
            "text": segment.get("narration_text") or safe_get(segment, "tts", "text") or "",
            "emotion": segment.get("emotion") or safe_get(segment, "tts", "emotion") or "",
            "duration_sec": float(duration or 0),
            "has_merged_video": bool(safe_get(segment, "merged", "merged_video_url")),
        }
        light.append(base)
        full.append({
            **base,
            "speed": segment.get("speed", ""),
            "debug_data_url": scene_meta.get("debug_data_url", ""),
            "scene_video_url": scene_meta.get("scene_video_url", ""),
            "video_url": safe_get(segment, "video", "video_url"),
            "original_video_url": safe_get(segment, "video", "original_video_url"),
            "audio_url": safe_get(segment, "tts", "audio_url"),
            "merged_video_url": safe_get(segment, "merged", "merged_video_url"),
            "keyframe_url": safe_get(segment, "keyframe", "image_url"),
            "grid_image_url": safe_get(segment, "keyframe", "grid_image_url"),
            "video_prompt": safe_get(segment, "video", "video_prompt"),
            "keyframe_prompt": safe_get(segment, "keyframe", "prompt"),
            "retrieval_status": "ready" if safe_get(segment, "merged", "merged_video_url") else "missing_merged_video",
        })
    return light, full


def main() -> int:
    parser = argparse.ArgumentParser(description="Build light/full segment pools for highlight retrieval.")
    parser.add_argument("node_outputs_json_url", help="Remote node_outputs.json URL")
    parser.add_argument("--out-dir", default="highlight_workspace/pool", help="Output directory")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent debug JSON downloads")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    main_json = fetch_json(args.node_outputs_json_url)
    scenes = main_json.get("scenes") or []
    scene_debug_urls = [
        {
            "scene_index": scene.get("scene_index") or index + 1,
            "debug_data_url": scene.get("debug_data_url", ""),
            "scene_video_url": scene.get("scene_video_url") or safe_get(scene, "scene_concat", "scene_video_url"),
            "segment_count": safe_get(scene, "summary", "segment_count", default=0),
        }
        for index, scene in enumerate(scenes)
        if scene.get("debug_data_url")
    ]

    debug_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(fetch_json, item["debug_data_url"]): item for item in scene_debug_urls}
        for future in as_completed(futures):
            meta = futures[future]
            try:
                debug_results.append((meta, future.result()))
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] failed to fetch scene {meta.get('scene_index')}: {exc}", file=sys.stderr)

    debug_results.sort(key=lambda pair: int(pair[0].get("scene_index") or 0))
    light_segments: list[dict[str, Any]] = []
    full_segments: list[dict[str, Any]] = []
    absolute_index = 0
    for meta, debug_data in debug_results:
        light, full = normalize_scene_debug(meta, debug_data, absolute_index)
        light_segments.extend(light)
        full_segments.extend(full)
        absolute_index += len(light)

    run_id = main_json.get("run_id") or Path(args.node_outputs_json_url).parent.name
    summary = {
        "episode_count": len(scene_debug_urls),
        "segment_count": len(light_segments),
        "available_merged_video_count": sum(1 for item in full_segments if item.get("merged_video_url")),
        "available_video_count": sum(1 for item in full_segments if item.get("video_url")),
        "available_audio_count": sum(1 for item in full_segments if item.get("audio_url")),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    common = {
        "source_json_url": args.node_outputs_json_url,
        "run_id": run_id,
        "summary": summary,
        "scene_debug_urls": scene_debug_urls,
    }
    light_pool = {
        "pool_version": "1.0",
        **common,
        "highlight_target": {
            "highlight_count": 10,
            "preferred_segment_count": 100,
            "segment_count_range": [80, 120],
            "target_duration": "2-3分钟高光段，后续随机选择1-2集连续素材补足到5-8分钟成片",
            "usage": "投放高光视频批量方案",
        },
        "segments": light_segments,
    }
    full_pool = {
        "pool_version": "1.0",
        **common,
        "segments": full_segments,
    }

    (out_dir / "scene_debug_urls.json").write_text(json.dumps(scene_debug_urls, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "light_segment_pool.json").write_text(json.dumps(light_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "full_segment_pool.json").write_text(json.dumps(full_pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

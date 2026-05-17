#!/usr/bin/env python3
"""Build one timeline JSON per highlight in a multi_highlight_plan."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_run_id(value: str) -> str:
    value = value or ""
    marker = "narration_final_process_"
    if marker in value:
        return marker + value.split(marker, 1)[1].split("/", 1)[0]
    return value


def duration_of(item: dict[str, Any]) -> float:
    try:
        return float(item.get("duration_sec") or 0)
    except (TypeError, ValueError):
        return 0.0


def timeline_item_from_segment(segment: dict[str, Any], order: int, edit_action: str, run_id: str) -> dict[str, Any]:
    gid = segment.get("global_segment_id") or f"scene_{segment.get('scene_index')}_seg_{segment.get('segment_index')}"
    preferred = segment.get("merged_video_url") or ""
    fallback = segment.get("video_url") or ""
    return {
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
        "edit_action": edit_action,
        "speed": 1.0,
        "local_filename": f"{run_id or 'unknown_run'}_{order:03d}_{gid}.mp4",
    }


def fill_timeline_with_random_segments(
    timeline_path: Path,
    pool_segments: list[dict[str, Any]],
    *,
    target_min_sec: float,
    target_max_sec: float,
    filler_episode_min: int,
    filler_episode_max: int,
    seed: int,
) -> dict[str, Any]:
    data = load_json(timeline_path)
    run_id = normalize_run_id(data.get("source_run_id", ""))
    timeline = data.get("timeline") or []
    used_ids = {item.get("global_segment_id") for item in timeline if item.get("global_segment_id")}
    current_duration = sum(duration_of(item) for item in timeline)
    base_duration = current_duration
    rng = random.Random(seed)
    by_episode: dict[int, list[dict[str, Any]]] = {}
    for item in pool_segments:
        if item.get("global_segment_id") in used_ids:
            continue
        if not (item.get("merged_video_url") or item.get("video_url")):
            continue
        try:
            episode = int(item.get("scene_index") or item.get("episode_id") or 0)
        except (TypeError, ValueError):
            episode = 0
        if episode <= 0:
            continue
        by_episode.setdefault(episode, []).append(item)
    for items in by_episode.values():
        items.sort(key=lambda item: int(item.get("segment_index") or 0))

    episodes = list(by_episode)
    rng.shuffle(episodes)
    episode_count = min(max(filler_episode_min, rng.randint(filler_episode_min, filler_episode_max)), len(episodes))
    selected_episodes = episodes[:episode_count]
    candidates: list[dict[str, Any]] = []
    for episode in selected_episodes:
        candidates.extend(by_episode.get(episode, []))

    added_count = 0
    for segment in candidates:
        if current_duration >= target_min_sec:
            break
        segment_duration = duration_of(segment)
        if segment_duration <= 0:
            segment_duration = 5.0
        if current_duration + segment_duration > target_max_sec:
            continue
        order = len(timeline) + 1
        timeline.append(timeline_item_from_segment(segment, order, "random_fill", run_id))
        used_ids.add(segment.get("global_segment_id"))
        current_duration += segment_duration
        added_count += 1

    data["timeline"] = timeline
    data["selected_segment_count"] = len(timeline)
    data["actual_duration_sec"] = round(current_duration, 3)
    data["fill_strategy"] = {
        "enabled": True,
        "target_min_sec": target_min_sec,
        "target_max_sec": target_max_sec,
        "filler_episode_min": filler_episode_min,
        "filler_episode_max": filler_episode_max,
        "selected_filler_episodes": selected_episodes,
        "base_duration_sec": round(base_duration, 3),
        "added_segment_count": added_count,
        "status": (
            "above_target_no_fill"
            if base_duration > target_max_sec
            else "already_in_range"
            if added_count == 0 and current_duration >= target_min_sec
            else "filled"
            if current_duration >= target_min_sec
            else "below_target_no_more_safe_candidates"
        ),
    }
    timeline_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data["fill_strategy"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build timelines for all highlights in a multi_highlight_plan.")
    parser.add_argument("highlight_plan", help="Path to highlight_plan.json")
    parser.add_argument("full_segment_pool", help="Path to full_segment_pool.json")
    parser.add_argument("--out-dir", default="workspace/plan/highlights", help="Output directory for highlight timelines")
    parser.add_argument("--fill-random", action="store_true", help="Append unused generated segments until each timeline reaches the target duration.")
    parser.add_argument("--target-min-sec", type=float, default=300, help="Minimum final duration after random fill.")
    parser.add_argument("--target-max-sec", type=float, default=480, help="Maximum final duration after random fill.")
    parser.add_argument("--filler-episode-min", type=int, default=1, help="Minimum number of episodes used for random filler.")
    parser.add_argument("--filler-episode-max", type=int, default=2, help="Maximum number of episodes used for random filler.")
    parser.add_argument("--seed", type=int, default=20260515, help="Random seed for repeatable filler selection.")
    args = parser.parse_args()

    plan_path = Path(args.highlight_plan).expanduser().resolve()
    pool_path = Path(args.full_segment_pool).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan: dict[str, Any] = load_json(plan_path)
    pool: dict[str, Any] = load_json(pool_path)
    plan_run_id = normalize_run_id(plan.get("source_run_id") or plan.get("run_id") or plan.get("source_json_url", ""))
    pool_run_id = normalize_run_id(pool.get("run_id") or pool.get("source_json_url", ""))
    if plan_run_id and pool_run_id and plan_run_id != pool_run_id:
        raise SystemExit(
            "highlight_plan 与 full_segment_pool 不是同一个任务，已停止生成多高光 timeline。\n"
            f"plan: {plan_run_id}\n"
            f"pool : {pool_run_id}\n"
            "请重新用当前任务的 Agent 结果生成 highlight_plan.json。"
        )
    pool_segments: list[dict[str, Any]] = pool.get("segments") or []
    highlights = plan.get("highlights") if isinstance(plan.get("highlights"), list) else [plan.get("highlight", {})]
    outputs = []
    fill_results = []
    for index, highlight in enumerate(highlights, start=1):
        highlight_id = highlight.get("highlight_id") or f"highlight_{index:02d}"
        out_path = out_dir / f"{highlight_id}_timeline.json"
        subprocess.run([
            sys.executable,
            str(Path(__file__).resolve().parent / "build_timeline.py"),
            str(plan_path),
            args.full_segment_pool,
            "--out",
            str(out_path),
        ], check=True)
        if args.fill_random:
            fill_results.append({
                "highlight_id": highlight_id,
                **fill_timeline_with_random_segments(
                    out_path,
                    pool_segments,
                    target_min_sec=args.target_min_sec,
                    target_max_sec=args.target_max_sec,
                    filler_episode_min=args.filler_episode_min,
                    filler_episode_max=args.filler_episode_max,
                    seed=args.seed + index,
                ),
            })
        outputs.append(str(out_path))
    print(json.dumps({
        "status": "ok",
        "highlight_count": len(outputs),
        "fill_random": bool(args.fill_random),
        "fill_results": fill_results,
        "outputs": outputs,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

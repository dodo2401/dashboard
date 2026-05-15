#!/usr/bin/env python3
"""Build an Agent-friendly input package from light_segment_pool.json."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


KEYWORDS = [
    "告发", "后妈", "继子", "别墅", "奢靡", "冲", "撞", "死", "杀", "打", "骂", "跪",
    "离婚", "结婚", "嫁妆", "怀孕", "孩子", "背叛", "复仇", "报复", "真相", "秘密",
    "千万", "亿", "钱", "合同", "威胁", "崩溃", "疯", "哭", "怒", "恨", "怕", "逃",
    "曝光", "直播", "全网", "打脸", "反转", "身份", "误会", "校霸", "豪门",
]

EMOTION_SCORE = {
    "生气": 3,
    "厌恶": 3,
    "恐惧": 3,
    "悲伤": 2,
    "惊讶": 2,
    "开心": 1,
}


def score_episode(items: list[dict[str, Any]], scene_index: int) -> float:
    score = 0.0
    text = "\n".join(str(item.get("text", "")) for item in items)
    for keyword in KEYWORDS:
        score += text.count(keyword) * 2
    for item in items:
        score += EMOTION_SCORE.get(str(item.get("emotion", "")), 0)
    if scene_index <= 3:
        score += 8
    if len(items) >= 20:
        score += 3
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert light_segment_pool.json into an Agent-friendly query package.")
    parser.add_argument("light_segment_pool", help="Path to light_segment_pool.json")
    parser.add_argument("--out-json", default="workspace/agent_input/highlight_agent_input.json", help="Output Agent input JSON")
    parser.add_argument("--out-txt", default="workspace/agent_input/highlight_agent_input.txt", help="Output Agent input text")
    parser.add_argument("--max-segments", type=int, default=0, help="Optional cap for debugging")
    parser.add_argument("--candidate-scenes", type=int, default=0, help="Only include top-N scored scenes for external Agent APIs")
    parser.add_argument("--full-format", action="store_true", help="Keep debug fields such as IDs, emotion and duration")
    args = parser.parse_args()

    pool_path = Path(args.light_segment_pool).expanduser().resolve()
    out_json = Path(args.out_json).expanduser().resolve()
    out_txt = Path(args.out_txt).expanduser().resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    pool: dict[str, Any] = json.loads(pool_path.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = pool.get("segments") or []
    if args.max_segments:
        segments = segments[:args.max_segments]

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for segment in segments:
        grouped[int(segment.get("scene_index") or segment.get("episode_id") or 0)].append(segment)
    for items in grouped.values():
        items.sort(key=lambda item: int(item.get("segment_index") or 0))

    selected_scene_indexes = sorted(grouped)
    scored_scenes = [
        {
            "scene_index": scene_index,
            "segment_count": len(items),
            "score": round(score_episode(items, scene_index), 3),
            "first_text": items[0].get("text", "") if items else "",
        }
        for scene_index, items in grouped.items()
    ]
    scored_scenes.sort(key=lambda item: (-float(item["score"]), int(item["scene_index"])))
    if args.candidate_scenes:
        selected_scene_indexes = sorted(int(item["scene_index"]) for item in scored_scenes[:args.candidate_scenes])

    episodes: list[dict[str, Any]] = []
    lines: list[str] = []
    for scene_index in selected_scene_indexes:
        items = grouped[scene_index]
        simple_segments = [
            {
                "episode": scene_index,
                "sentence": int(item.get("segment_index", 0)) + 1,
                "text": item.get("text", ""),
            }
            for item in items
        ]
        debug_segments = [
            {
                "episode": scene_index,
                "sentence": int(item.get("segment_index", 0)) + 1,
                "global_segment_id": item.get("global_segment_id"),
                "absolute_index": item.get("absolute_index"),
                "text": item.get("text", ""),
                "emotion": item.get("emotion", ""),
                "duration_sec": item.get("duration_sec") or 0,
            }
            for item in items
        ]
        episodes.append({
            "episode": scene_index,
            "segments": debug_segments if args.full_format else simple_segments,
        })
        lines.append(f"【第{scene_index}集】")
        for item in items:
            lines.append(f"{scene_index}-{int(item.get('segment_index', 0)) + 1}. {item.get('text', '')}")
        lines.append("")

    output_schema = {
        "highlights": [
            {
                "title": "高光标题1",
                "reason": "选择理由",
                "target_duration": "2-3分钟",
                "target_sentence_count": 100,
                "shots": [
                    {
                        "episode": 1,
                        "sentence": 1
                    }
                ]
            }
        ]
    }

    summary = pool.get("summary") or {}
    target = {
        **(pool.get("highlight_target") or {}),
        "highlight_count": 10,
        "preferred_segment_count": 100,
        "segment_count_range": [80, 120],
        "target_duration": "2-3分钟高光段，后续随机补足到5-8分钟成片",
    }
    query = "\n".join([
        "你是短剧/小说解说投放高光剪辑策划 Agent。",
        "请从下面已经生成好的分集分句素材中，选择 10 条适合投放的高光视频方案。",
        "重要：不要改写原文，不要生成新台词，只能选择已有分句。",
        "你只需要返回分集 episode、句子序号 sentence。",
        "",
        f"分集数：{summary.get('episode_count', 0)}",
        f"分句数：{summary.get('segment_count', 0)}",
        f"建议选择分句数：{target.get('segment_count_range', [60, 90])}",
        "",
        "选择要求：",
        "1. 一次输出 10 条 highlights，每条高光段控制在 2-3 分钟左右，优先约 100 句。",
        "2. 每条开头 3-8 句必须有强钩子：冲突、反转、悬念、身份错位、危机或强情绪。",
        "3. 每条中段必须有因果推进，不能只堆砌金句。",
        "4. 每条结尾停在爽点、反转、悬念或强情绪节点。",
        "5. 每条尽量选择同一主线连续分句，允许少量跨段，但观众必须能看懂。",
        "6. 每条 shots 数组只返回你选择的句子，字段只需要 episode 和 sentence。",
        "7. 下游会随机补足剩余分集素材，把每条最终视频控制到 5-8 分钟，所以这里不要为了凑时长选择弱剧情。",
        "",
        "必须输出纯 JSON，字段越少越好，格式如下：",
        json.dumps(output_schema, ensure_ascii=False),
        "",
        "可选句子：",
        "\n".join(lines),
    ])

    agent_input = {
        "input_version": "1.0",
        "source_json_url": pool.get("source_json_url", ""),
        "run_id": pool.get("run_id", ""),
        "summary": summary,
        "highlight_target": target,
        "agent_payload": {
            "task": "从已生成视频素材池中选择10个投放高光组合",
            "rules": [
                "只选择已有分句，不改写原文，不生成新台词",
                "每个组合约100句，对应2-3分钟高光段",
                "输出10个highlights，每个highlight只需要shots数组",
                "shots字段只保留episode和sentence",
                "后续拼接链路会随机补足剩余分集素材到5-8分钟"
            ],
            "output_format": output_schema,
            "episodes": episodes,
        },
        "candidate_policy": {
            "enabled": bool(args.candidate_scenes),
            "candidate_scene_count": len(selected_scene_indexes),
            "selected_scene_indexes": selected_scene_indexes,
            "top_scored_scenes": scored_scenes[: max(args.candidate_scenes or 10, 10)],
        },
        "agent_query": query,
        "episodes": episodes,
    }
    out_json.write_text(json.dumps(agent_input, ensure_ascii=False, indent=2), encoding="utf-8")
    out_txt.write_text(query, encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "episodes": len(episodes),
        "segments": len(segments),
        "out_json": str(out_json),
        "out_txt": str(out_txt),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

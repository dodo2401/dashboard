#!/usr/bin/env python3
"""Validate and save manually returned Agent output as highlight_plan.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def strip_markdown(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def load_json_or_text_json(path: Path) -> Any:
    text = strip_markdown(path.read_text(encoding="utf-8"))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        repaired = text.strip()
        if repaired.startswith("{") and repaired.endswith("}") and re.search(r"^\s*\{\s*\n\s*\{", repaired):
            repaired = "[" + repaired[1:-1].strip() + "]"
            repaired = re.sub(r",\s*\]$", "]", repaired)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise SystemExit(f"Agent output is not valid JSON: {exc}") from exc


def build_segment_lookup(full_segment_pool: Path) -> dict[tuple[int, int], dict[str, Any]]:
    data = json.loads(full_segment_pool.read_text(encoding="utf-8"))
    lookup: dict[tuple[int, int], dict[str, Any]] = {}
    for item in data.get("segments", []):
        episode = int(item.get("scene_index") or item.get("episode_id") or 0)
        sentence = int(item.get("segment_index") or 0) + 1
        lookup[(episode, sentence)] = item
    return lookup


def normalize_plan(data: Any, lookup: dict[tuple[int, int], dict[str, Any]] | None = None) -> dict[str, Any]:
    if isinstance(data, list):
        highlight = {
            "title": "高光片段",
            "reason": "",
            "shots": data,
        }
        data = {"highlight": highlight}
    elif not isinstance(data, dict):
        raise SystemExit("Agent output must be a JSON object or a JSON array.")
    elif "highlight" in data:
        highlight = data.get("highlight") or {}
    else:
        highlight = data

    shots = highlight.get("shots")
    if not isinstance(shots, list) or not shots:
        raise SystemExit("Agent output missing required field: shots")

    normalized_shots: list[dict[str, Any]] = []
    for index, shot in enumerate(shots, start=1):
        episode = int(shot.get("episode") or shot.get("scene_index") or 0)
        sentence = int(shot.get("sentence") or 0)
        segment = lookup.get((episode, sentence)) if lookup else None
        if lookup and not segment:
            raise SystemExit(f"Cannot map shot to segment: episode={episode}, sentence={sentence}")
        normalized_shots.append({
            "order": index,
            "global_segment_id": segment.get("global_segment_id") if segment else shot.get("global_segment_id", ""),
            "scene_index": episode or shot.get("scene_index"),
            "segment_index": (sentence - 1) if sentence else shot.get("segment_index", 0),
            "source_text": (segment.get("text") if segment else shot.get("text") or shot.get("source_text") or ""),
            "highlight_function": shot.get("highlight_function", "hook" if index <= 3 else "conflict"),
            "reason": shot.get("reason", ""),
            "priority": shot.get("priority", "must_keep"),
        })

    return {
        "task_type": "single_highlight_plan",
        "source_run_id": highlight.get("source_run_id", data.get("source_run_id", "")),
        "source_json_url": highlight.get("source_json_url", data.get("source_json_url", "")),
        "highlight": {
            "highlight_id": highlight.get("highlight_id", "highlight_01"),
            "title": highlight.get("title", data.get("title", "高光片段")),
            "selling_point": highlight.get("selling_point", data.get("reason", "")),
            "hook": highlight.get("hook", normalized_shots[0]["source_text"] if normalized_shots else ""),
            "selected_segment_count": len(normalized_shots),
            "storyline": highlight.get("storyline", data.get("reason", "")),
            "blocks": highlight.get("blocks", []),
            "shots": normalized_shots,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Save manually returned Agent output as highlight_plan.json.")
    parser.add_argument("agent_output", help="Path to Agent returned JSON/TXT")
    parser.add_argument("--out", default="workspace/plan/highlight_plan.json", help="Output highlight_plan.json")
    parser.add_argument("--full-segment-pool", default="workspace/pool/full_segment_pool.json", help="Path to full_segment_pool.json for episode/sentence mapping")
    args = parser.parse_args()

    source = Path(args.agent_output).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    full_segment_pool = Path(args.full_segment_pool).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    lookup = build_segment_lookup(full_segment_pool) if full_segment_pool.exists() else None
    plan = normalize_plan(load_json_or_text_json(source), lookup)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "out": str(out),
        "selected_segment_count": plan.get("highlight", {}).get("selected_segment_count"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

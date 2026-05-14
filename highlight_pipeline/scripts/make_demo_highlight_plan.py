#!/usr/bin/env python3
"""Create a deterministic demo highlight_plan.json from a light segment pool.

This is a smoke-test replacement for the future highlight agent. It selects a
continuous block from the start of the story so retrieval and concat can be
validated before wiring in the agent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a demo highlight plan from a light segment pool.")
    parser.add_argument("light_segment_pool", help="Path to light_segment_pool.json")
    parser.add_argument("--out", default="highlight_workspace/plan/highlight_plan.json", help="Output highlight_plan.json")
    parser.add_argument("--count", type=int, default=12, help="Number of continuous segments to select")
    parser.add_argument("--start", type=int, default=0, help="Absolute start index")
    args = parser.parse_args()

    pool_path = Path(args.light_segment_pool).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = pool.get("segments") or []
    selected = segments[args.start:args.start + args.count]
    if not selected:
        raise SystemExit("No segments selected. Check --start/--count.")

    plan = {
        "task_type": "single_highlight_plan",
        "source_run_id": pool.get("run_id", ""),
        "highlight": {
            "highlight_id": "highlight_01",
            "title": "Demo 高光片段",
            "selling_point": "验证高光分句回捞和本地拼接链路",
            "hook": selected[0].get("text", ""),
            "selected_segment_count": len(selected),
            "blocks": [
                {
                    "block_id": "block_01",
                    "function": "hook",
                    "summary": "连续选取的 demo 高光片段，用于验证链路",
                    "scene_index": selected[0].get("scene_index"),
                    "start_global_segment_id": selected[0].get("global_segment_id"),
                    "end_global_segment_id": selected[-1].get("global_segment_id"),
                    "segment_count": len(selected),
                    "priority": "must_keep",
                }
            ],
            "shots": [
                {
                    "order": index + 1,
                    "global_segment_id": segment.get("global_segment_id"),
                    "scene_index": segment.get("scene_index"),
                    "segment_index": segment.get("segment_index"),
                    "source_text": segment.get("text", ""),
                    "highlight_function": "hook" if index < 3 else "build_up",
                    "reason": "demo 连续片段",
                    "priority": "must_keep",
                }
                for index, segment in enumerate(selected)
            ],
        },
    }
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

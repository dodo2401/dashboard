#!/usr/bin/env python3
"""Prepare external Agent input from a node_outputs.json URL.

This is the manual-API bridge:
node_outputs.json URL -> segment pools -> Agent-friendly JSON/TXT input.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Agent input package from node_outputs.json URL.")
    parser.add_argument("node_outputs_json_url", help="Remote node_outputs.json URL")
    parser.add_argument("--workspace", default=str(ROOT / "workspace"), help="Workspace directory")
    parser.add_argument("--candidate-scenes", type=int, default=0, help="Top-N scored scenes included in Agent input; default 0 means all scenes in order")
    parser.add_argument("--max-segments", type=int, default=0, help="Optional cap for debug only")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    pool_dir = workspace / "pool"
    agent_dir = workspace / "agent_input"
    agent_json = agent_dir / "highlight_agent_input.json"
    agent_txt = agent_dir / "highlight_agent_input.txt"

    run([
        sys.executable,
        str(SCRIPTS / "build_segment_pool.py"),
        args.node_outputs_json_url,
        "--out-dir",
        str(pool_dir),
    ])

    cmd = [
        sys.executable,
        str(SCRIPTS / "build_agent_input.py"),
        str(pool_dir / "light_segment_pool.json"),
        "--out-json",
        str(agent_json),
        "--out-txt",
        str(agent_txt),
        "--candidate-scenes",
        str(args.candidate_scenes),
    ]
    if args.max_segments:
        cmd.extend(["--max-segments", str(args.max_segments)])
    run(cmd)

    print("")
    print("已生成外部 Agent 手动输入：")
    print(f"JSON: {agent_json}")
    print(f"TXT : {agent_txt}")
    print("")
    print("推荐手动复制 TXT 内容，或把 JSON 中的 agent_query 字段填入外部 API 页面。")
    print("外部 Agent 输出后，请保存为：")
    print(workspace / "plan" / "highlight_plan.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

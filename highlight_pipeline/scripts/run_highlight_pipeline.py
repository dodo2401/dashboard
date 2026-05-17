#!/usr/bin/env python3
"""One-command runner for the highlight pipeline.

This script glues the deterministic nodes together:
node_outputs URL -> segment pools -> highlight plan -> retrieval timeline -> optional download/concat.

Use a real agent by passing --agent-plan. Use --demo only for smoke tests.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the highlight pipeline from node_outputs.json to timeline/download.")
    parser.add_argument("node_outputs_json_url", help="Remote node_outputs.json URL")
    parser.add_argument("--workspace", default=str(ROOT / "workspace"), help="Workspace directory")
    parser.add_argument("--agent-plan", default="", help="Path to a real Agent-produced highlight_plan.json")
    parser.add_argument("--agent-api", default="", help="External Agent API URL that returns highlight_plan.json")
    parser.add_argument("--agent-unwrap-field", default="", help="Dot path to actual JSON result in Agent API response")
    parser.add_argument("--agent-candidate-scenes", type=int, default=10, help="Top-N scored scenes included in external Agent input")
    parser.add_argument("--demo", action="store_true", help="Create a demo highlight_plan.json for smoke testing")
    parser.add_argument("--demo-count", type=int, default=12, help="Demo selected segment count")
    parser.add_argument("--demo-start", type=int, default=0, help="Demo start absolute index")
    parser.add_argument("--download", action="store_true", help="Download clips and concat when ffmpeg is available")
    parser.add_argument("--download-limit", type=int, default=0, help="Download only first N clips for smoke testing")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing clips when running download step")
    parser.add_argument("--target-min-sec", type=float, default=300, help="Minimum final duration for each multi-highlight output.")
    parser.add_argument("--target-max-sec", type=float, default=480, help="Maximum final duration for each multi-highlight output.")
    parser.add_argument("--filler-episode-min", type=int, default=1, help="Minimum number of episodes used for random filler.")
    parser.add_argument("--filler-episode-max", type=int, default=2, help="Maximum number of episodes used for random filler.")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    pool_dir = workspace / "pool"
    plan_dir = workspace / "plan"
    plan_path = plan_dir / "highlight_plan.json"
    timeline_path = plan_dir / "highlight_timeline.json"
    timelines_dir = plan_dir / "highlights"
    agent_input_path = workspace / "agent_input" / "highlight_agent_input.json"
    plan_dir.mkdir(parents=True, exist_ok=True)

    run([
        sys.executable,
        str(SCRIPTS / "build_segment_pool.py"),
        args.node_outputs_json_url,
        "--out-dir",
        str(pool_dir),
    ])

    run([
        sys.executable,
        str(SCRIPTS / "build_agent_input.py"),
        str(pool_dir / "light_segment_pool.json"),
        "--out-json",
        str(agent_input_path),
        "--out-txt",
        str(workspace / "agent_input" / "highlight_agent_input.txt"),
        "--candidate-scenes",
        str(args.agent_candidate_scenes if args.agent_api else 0),
    ])

    if args.agent_plan:
        source_plan = Path(args.agent_plan).expanduser().resolve()
        if not source_plan.exists():
            raise SystemExit(f"Agent plan not found: {source_plan}")
        shutil.copyfile(source_plan, plan_path)
        print(f"copied agent plan: {source_plan} -> {plan_path}")
    elif args.agent_api:
        cmd = [
            sys.executable,
            str(SCRIPTS / "call_external_agent.py"),
            "--api-url",
            args.agent_api,
            "--input",
            str(agent_input_path),
            "--prompt",
            str(ROOT / "highlight_agent_prompt.md"),
            "--out",
            str(plan_path),
        ]
        if args.agent_unwrap_field:
            cmd.extend(["--unwrap-field", args.agent_unwrap_field])
        run(cmd)
    elif args.demo:
        run([
            sys.executable,
            str(SCRIPTS / "make_demo_highlight_plan.py"),
            str(pool_dir / "light_segment_pool.json"),
            "--out",
            str(plan_path),
            "--count",
            str(args.demo_count),
            "--start",
            str(args.demo_start),
        ])
    else:
        print("")
        print("素材池已生成，下一步请让高光 Agent 读取：")
        print(agent_input_path)
        print("")
        print("并输出 highlight_plan.json 到：")
        print(plan_path)
        print("")
        print("Agent 提示词：")
        print(ROOT / "highlight_agent_prompt.md")
        print("")
        print("如果使用外部 Agent API，可直接运行：")
        print(f"{sys.executable} {__file__} \"{args.node_outputs_json_url}\" --workspace {workspace} --agent-api <agent_api_url>")
        print("")
        print("如果手动拿到 Agent 输出后，继续运行：")
        print(f"{sys.executable} {__file__} \"{args.node_outputs_json_url}\" --workspace {workspace} --agent-plan {plan_path}")
        return 0

    run([
        sys.executable,
        str(SCRIPTS / "build_multi_highlight_timelines.py"),
        str(plan_path),
        str(pool_dir / "full_segment_pool.json"),
        "--out-dir",
        str(timelines_dir),
        "--fill-random",
        "--target-min-sec",
        str(args.target_min_sec),
        "--target-max-sec",
        str(args.target_max_sec),
        "--filler-episode-min",
        str(args.filler_episode_min),
        "--filler-episode-max",
        str(args.filler_episode_max),
    ])

    if args.download:
        cmd = [
            sys.executable,
            str(SCRIPTS / "download_multi_highlights.py"),
            "--timeline-dir",
            str(timelines_dir),
            "--workspace",
            str(workspace / "highlight_outputs"),
        ]
        if args.download_limit:
            cmd.extend(["--limit", str(args.download_limit)])
        if args.skip_download:
            cmd.append("--skip-download")
        run(cmd)
    else:
        print("")
        print("多高光时间线已生成：")
        print(timelines_dir)
        print("")
        print("如需下载拼接，继续运行：")
        print(f"{sys.executable} {SCRIPTS / 'download_multi_highlights.py'} --timeline-dir {timelines_dir} --workspace {workspace / 'highlight_outputs'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Import external Agent output from clipboard or file into highlight_plan.json."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from save_agent_output import build_segment_lookup, load_json_or_text_json, normalize_plan


ROOT = Path(__file__).resolve().parents[1]


def read_clipboard() -> str:
    if not shutil.which("pbpaste"):
        raise SystemExit("pbpaste not found. Please pass --input /path/to/agent_output.txt instead.")
    result = subprocess.run(["pbpaste"], text=True, capture_output=True, check=True)
    text = result.stdout.strip()
    if not text:
        raise SystemExit("Clipboard is empty. Copy the external Agent JSON result first.")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Import external Agent output and build highlight_plan.json.")
    parser.add_argument("--input", default="", help="Optional path to Agent output JSON/TXT. Defaults to macOS clipboard.")
    parser.add_argument("--workspace", default=str(ROOT / "workspace"), help="Highlight pipeline workspace directory.")
    parser.add_argument("--out", default="", help="Output highlight_plan.json path. Defaults to <workspace>/plan/highlight_plan.json.")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    plan_dir = workspace / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    manual_output = plan_dir / "manual_agent_output.txt"
    out = Path(args.out).expanduser().resolve() if args.out else plan_dir / "highlight_plan.json"
    full_segment_pool = workspace / "pool" / "full_segment_pool.json"
    if not full_segment_pool.exists():
        raise SystemExit(f"Missing full_segment_pool.json: {full_segment_pool}\nRun prepare_agent_input.py first.")

    if args.input:
        source = Path(args.input).expanduser().resolve()
        if not source.exists():
            raise SystemExit(f"Agent output file not found: {source}")
        manual_output.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        manual_output.write_text(read_clipboard(), encoding="utf-8")

    pool = json.loads(full_segment_pool.read_text(encoding="utf-8"))
    lookup = build_segment_lookup(full_segment_pool)
    plan = normalize_plan(load_json_or_text_json(manual_output), lookup)
    plan.setdefault("source_run_id", pool.get("run_id", ""))
    plan.setdefault("source_json_url", pool.get("source_json_url", ""))
    if not plan.get("source_run_id"):
        plan["source_run_id"] = pool.get("run_id", "")
    if not plan.get("source_json_url"):
        plan["source_json_url"] = pool.get("source_json_url", "")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "manual_output": str(manual_output),
        "out": str(out),
        "source_run_id": plan.get("source_run_id"),
        "source_json_url": plan.get("source_json_url"),
        "highlight_count": len(plan.get("highlights", [])) or 1,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

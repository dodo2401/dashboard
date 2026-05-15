#!/usr/bin/env python3
"""Call an external highlight Agent API and save highlight_plan.json.

The API contract can vary by platform, so this adapter keeps the payload simple
and configurable:
- default body: {"input": <light_segment_pool>, "prompt": <prompt text>}
- use --input-field / --prompt-field if the API expects different field names
- use --unwrap-field if the useful JSON is nested in the response
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def try_json_loads(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return value
    return value


def unwrap_response(response: Any, unwrap_field: str) -> Any:
    if unwrap_field:
        current = response
        for part in unwrap_field.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                raise SystemExit(f"Cannot unwrap field '{unwrap_field}' from response.")
        return try_json_loads(current)

    if isinstance(response, dict):
        for key in ("highlight_plan", "result", "output", "data", "content", "text"):
            if key in response:
                candidate = try_json_loads(response[key])
                if isinstance(candidate, dict) and ("highlight" in candidate or "highlights" in candidate or "task_type" in candidate):
                    return candidate
        return response
    return try_json_loads(response)


def find_plan(value: Any, path: str = "$") -> tuple[dict[str, Any] | None, str]:
    value = try_json_loads(value)
    if isinstance(value, dict) and ("highlight" in value or "highlights" in value):
        return value, path
    if isinstance(value, dict):
        for key, child in value.items():
            found, found_path = find_plan(child, f"{path}.{key}")
            if found is not None:
                return found, found_path
    if isinstance(value, list):
        for index, child in enumerate(value):
            found, found_path = find_plan(child, f"{path}.{index}")
            if found is not None:
                return found, found_path
    return None, ""


def validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise SystemExit("Agent response is not a JSON object.")
    if isinstance(plan.get("highlights"), list):
        if not plan["highlights"]:
            raise SystemExit("Agent response missing required field: highlights")
        for index, highlight in enumerate(plan["highlights"], start=1):
            shots = highlight.get("shots") if isinstance(highlight, dict) else None
            if not isinstance(shots, list) or not shots:
                raise SystemExit(f"Agent response missing required field: highlights[{index}].shots")
            highlight.setdefault("highlight_id", f"highlight_{index:02d}")
            highlight.setdefault("selected_segment_count", len(shots))
        plan.setdefault("task_type", "multi_highlight_plan")
        plan.setdefault("highlight_count", len(plan["highlights"]))
        plan.setdefault("highlight", plan["highlights"][0])
        return plan
    if "highlight" not in plan:
        raise SystemExit("Agent response missing required field: highlight")
    shots = plan.get("highlight", {}).get("shots")
    if not isinstance(shots, list) or not shots:
        raise SystemExit("Agent response missing required field: highlight.shots")
    selected_count = plan.get("highlight", {}).get("selected_segment_count")
    if selected_count != len(shots):
        plan.setdefault("highlight", {})["selected_segment_count"] = len(shots)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Call external highlight Agent API.")
    parser.add_argument("--api-url", required=True, help="External Agent API URL")
    parser.add_argument("--input", default="workspace/agent_input/highlight_agent_input.json", help="Path to Agent input JSON")
    parser.add_argument("--prompt", default=str(Path(__file__).resolve().parents[1] / "highlight_agent_prompt.md"), help="Path to prompt markdown")
    parser.add_argument("--out", default="workspace/plan/highlight_plan.json", help="Output highlight_plan.json")
    parser.add_argument("--input-field", default="input", help="Payload field name for the light pool")
    parser.add_argument("--prompt-field", default="prompt", help="Payload field name for prompt text")
    parser.add_argument("--unwrap-field", default="", help="Dot path to the actual JSON result in API response, e.g. data.output")
    parser.add_argument("--bearer-env", default="AISTUDIO_TOKEN", help="Env var name for Bearer token, if needed")
    parser.add_argument("--timeout", type=int, default=180, help="HTTP timeout seconds")
    parser.add_argument("--raw-out", default="", help="Optional path to save raw API response JSON")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    prompt_path = Path(args.prompt).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    input_data = load_json(input_path)
    agent_payload = input_data.get("agent_payload") if isinstance(input_data, dict) else None
    agent_query = input_data.get("agent_query") if isinstance(input_data, dict) else None
    payload_input = agent_payload or agent_query or input_data
    payload = {
        args.input_field: payload_input,
    }
    if not agent_payload and not agent_query:
        payload[args.prompt_field] = prompt_path.read_text(encoding="utf-8")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "highlight-pipeline/1.0",
    }
    token = os.environ.get(args.bearer_env, "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(args.api_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(detail, file=sys.stderr)
        raise SystemExit(f"Agent API HTTP {exc.code}: {exc.reason}") from exc

    try:
        response = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(raw[:2000], file=sys.stderr)
        raise SystemExit("Agent API did not return valid JSON.") from exc

    raw_out = Path(args.raw_out).expanduser().resolve() if args.raw_out else out_path.with_name("agent_raw_response.json")
    raw_out.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

    candidate = unwrap_response(response, args.unwrap_field)
    found_plan, found_path = find_plan(candidate)
    if found_plan is None:
        print(f"Saved raw Agent response: {raw_out}", file=sys.stderr)
        if isinstance(response, dict):
            print(f"Top-level response keys: {list(response.keys())}", file=sys.stderr)
        raise SystemExit("Agent response missing required field: highlight/highlights")

    plan = validate_plan(found_plan)
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "out": str(out_path),
        "raw_out": str(raw_out),
        "plan_path_in_response": found_path,
        "highlight_count": len(plan.get("highlights", [])) or 1,
        "selected_segment_count": plan.get("highlight", {}).get("selected_segment_count"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from app.agent.prompt import build_system_prompt
from app.config import Settings
from app.llm.router import ModelRouter, ModelTarget
from app.tools import server_tools


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return (
        "".join(ch for ch in nfkd if not unicodedata.combining(ch))
        .replace("đ", "d")
        .replace("Đ", "D")
    )


def _norm_text(value: str) -> str:
    return " ".join(_strip_accents(value).lower().strip().split())


def _parse_args_dict(raw: str | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _match_arg(key: str, expected_val: Any, actual_val: Any) -> bool:
    if expected_val is None or actual_val is None:
        return expected_val is actual_val
    if isinstance(expected_val, dict):
        return _match_args(expected_val, actual_val)
    if isinstance(expected_val, list):
        if not isinstance(actual_val, list) or len(expected_val) != len(actual_val):
            return False
        if key == "items":
            # Batch priorities are assigned by task ID, regardless of item order.
            unmatched = actual_val.copy()
            for expected in expected_val:
                for index, actual in enumerate(unmatched):
                    if _match_arg("", expected, actual):
                        unmatched.pop(index)
                        break
                else:
                    return False
            return True
        return all(
            _match_arg("", expected, actual)
            for expected, actual in zip(expected_val, actual_val, strict=True)
        )
    if key in ("deadline", "from", "to", "remindAt", "dueFrom", "dueTo"):
        try:
            exp_dt = datetime.fromisoformat(str(expected_val))
            act_dt = datetime.fromisoformat(str(actual_val))
            # Chấp nhận sai lệch <= 59 giây (vd 23:59:00 vs 23:59:59 ở cuối ngày)
            return abs((exp_dt - act_dt).total_seconds()) <= 59
        except (ValueError, TypeError):
            return str(expected_val) == str(actual_val)
    if key in ("title", "query", "message", "reason", "description"):
        return isinstance(actual_val, str) and _norm_text(expected_val) in _norm_text(actual_val)
    return type(expected_val) is type(actual_val) and expected_val == actual_val


def _match_args(expected: dict[str, Any], actual: Any) -> bool:
    return (
        isinstance(actual, dict)
        and expected.keys() == actual.keys()
        and all(_match_arg(key, value, actual[key]) for key, value in expected.items())
    )


def _score_case(
    expected_list: list[dict[str, Any]], actual_calls: list[dict[str, Any]]
) -> tuple[bool, bool]:
    tool_ok = [step["tool"] for step in expected_list] == [call["name"] for call in actual_calls]
    args_ok = tool_ok and all(
        _match_args(step.get("args", {}), call["arguments"])
        for step, call in zip(expected_list, actual_calls, strict=True)
    )
    return tool_ok, args_ok


async def _collect_calls(
    router: ModelRouter,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    row: dict[str, Any],
    actual_calls: list[dict[str, Any]],
    max_tool_steps: int,
) -> str:
    expected = row["expect"]
    fixtures = row.get("tool_results", [])
    multi_step = row["group"] == "multi_step"
    for _ in range(max_tool_steps + 1 if multi_step else 1):
        response = await router.complete(messages, tools, task_kind="chat")
        calls = [
            {"name": tc.name, "arguments": _parse_args_dict(tc.arguments)}
            for tc in response.tool_calls
        ]
        start = len(actual_calls)
        actual_calls.extend(calls)
        if not calls or not multi_step or len(actual_calls) > len(expected):
            return response.content
        if start < len(fixtures) and len(calls) > 1:
            raise ValueError("A dependent tool call must wait for the eval fixture result")
        if [call["name"] for call in actual_calls] != [
            step["tool"] for step in expected[: len(actual_calls)]
        ]:
            return response.content

        messages.append(
            {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                tc.arguments
                                if isinstance(tc.arguments, str)
                                else json.dumps(tc.arguments, ensure_ascii=False)
                            ),
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
        )
        for index, tc in enumerate(response.tool_calls, start):
            result = {"ok": True}
            if not _match_args(expected[index].get("args", {}), actual_calls[index]["arguments"]):
                result = {"error": "No matching eval fixture"}
            elif index < len(fixtures):
                result = fixtures[index]
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    raise RuntimeError("Eval exceeded the tool step limit")


async def run_eval(
    *,
    cases_path: Path,
    out_path: Path,
    target_model: ModelTarget,
    model_name_override: str | None,
    limit: int | None,
    timeout_s: float,
    delay_s: float = 0.0,
) -> dict[str, Any]:
    settings = Settings()
    if target_model == "small":
        settings.router_mode = "small_only"
        settings.small_timeout_s = timeout_s
        if model_name_override:
            settings.small_model_name = model_name_override
    else:
        settings.router_mode = "cloud_only"
        settings.cloud_timeout_s = timeout_s

    router = ModelRouter(settings)
    build_registry = getattr(server_tools, "build_p0_registry", None)
    registry = (build_registry or server_tools.build_phase1_registry)()
    tools = registry.specs()

    rows = await asyncio.to_thread(
        lambda: [
            json.loads(line)
            for line in cases_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    )
    if limit is not None:
        rows = rows[:limit]

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    tool_pass = 0
    args_pass = 0

    for row in rows:
        now = datetime.fromisoformat(row["now"])
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(now)},
            {"role": "user", "content": row["message"]},
        ]
        started = time.monotonic()
        error_str = None
        assistant_text = ""
        actual_calls: list[dict[str, Any]] = []
        try:
            assistant_text = await _collect_calls(
                router, messages, tools, row, actual_calls, settings.max_tool_steps
            )
        except Exception as exc:
            error_str = str(exc)

        elapsed = time.monotonic() - started
        latencies.append(elapsed)
        if error_str is not None or (not row["expect"] and not assistant_text.strip()):
            t_ok, a_ok = False, False
        else:
            t_ok, a_ok = _score_case(row["expect"], actual_calls)
        if t_ok:
            tool_pass += 1
        if a_ok:
            args_pass += 1

        results.append(
            {
                "id": row["id"],
                "group": row["group"],
                "message": row["message"],
                "expected": row["expect"],
                "actual": actual_calls,
                "toolOk": t_ok,
                "argsOk": a_ok,
                "seconds": round(elapsed, 3),
                "error": error_str,
                "assistantText": assistant_text,
            }
        )
        print(
            f"[{row['id']}] tool={'OK' if t_ok else 'FAIL'} args={'OK' if a_ok else 'FAIL'} "
            f"({elapsed:.3f}s) -> {[c['name'] for c in actual_calls]}",
            flush=True,
        )
        if delay_s > 0:
            await asyncio.sleep(delay_s)

    total = len(results)
    sorted_lat = sorted(latencies)
    p50 = median(sorted_lat) if sorted_lat else 0.0
    p95_idx = min(len(sorted_lat) - 1, math.ceil(0.95 * len(sorted_lat)) - 1) if sorted_lat else 0
    p95 = sorted_lat[p95_idx] if sorted_lat else 0.0

    report = {
        "target": target_model,
        "modelName": settings.small_model_name if target_model == "small" else settings.cloud_model,
        "total": total,
        "toolCorrect": tool_pass,
        "toolAccuracy": round(tool_pass / total, 4) if total else 0.0,
        "argsCorrect": args_pass,
        "argsAccuracy": round(args_pass / total, 4) if total else 0.0,
        "p50Seconds": round(p50, 3),
        "p95Seconds": round(p95, 3),
        "results": results,
    }
    await asyncio.to_thread(
        lambda: (
            out_path.parent.mkdir(parents=True, exist_ok=True),
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"),
        )
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy eval AI Harness")
    parser.add_argument("--model", choices=["small", "cloud"], default="small")
    parser.add_argument("--model-name", default=None, help="Ghi đè SMALL_MODEL_NAME (vd qwen3:8b)")
    parser.add_argument("--cases", type=Path, default=Path("eval/cases.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("eval/report-small.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--delay", type=float, default=0.0, help="Nghỉ giữa các câu (giây)")
    args = parser.parse_args()

    report = asyncio.run(
        run_eval(
            cases_path=args.cases,
            out_path=args.out,
            target_model=args.model,
            model_name_override=args.model_name,
            limit=args.limit,
            timeout_s=args.timeout,
            delay_s=args.delay,
        )
    )
    print(
        f"\nSUMMARY: tool={report['toolCorrect']}/{report['total']} "
        f"({report['toolAccuracy'] * 100:.1f}%), "
        f"args={report['argsCorrect']}/{report['total']} ({report['argsAccuracy'] * 100:.1f}%), "
        f"p50={report['p50Seconds']}s, p95={report['p95Seconds']}s"
    )


if __name__ == "__main__":
    main()

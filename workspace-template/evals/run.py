#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from qiqi_eval.runner import RunnerOptions, run_scenario, run_suite
from qiqi_eval.scenario import load_scenario


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def main() -> int:
    eval_root = Path(__file__).resolve().parent
    workspace_root = eval_root.parent
    parser = argparse.ArgumentParser(
        description="Run headless end-to-end QiQi orchestration evaluations."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", type=Path)
    group.add_argument("--suite")
    parser.add_argument("--runs", type=_positive_int)
    parser.add_argument("--parent-route", default="codex-balanced")
    parser.add_argument("--timeout-seconds", type=_positive_int, default=3600)
    parser.add_argument("--output-dir", type=Path, default=workspace_root / ".eval-results")
    parser.add_argument("--keep-workspace-on-failure", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate scenario/fixture references without launching native agents.",
    )
    args = parser.parse_args()

    if args.scenario:
        scenario_path = args.scenario.resolve()
        if args.validate_only:
            scenario = load_scenario(scenario_path)
            if not scenario.fixture.is_file():
                raise SystemExit(f"missing fixture: {scenario.fixture}")
            print(json.dumps({"scenario": scenario.id, "fixture": str(scenario.fixture)}))
            return 0
    else:
        suite_dir = (eval_root / "suites" / args.suite).resolve()
        if args.validate_only:
            paths = sorted(suite_dir.glob("*.yaml"))
            if not paths:
                raise SystemExit(f"suite has no YAML scenarios: {suite_dir}")
            for path in paths:
                scenario = load_scenario(path)
                if not scenario.fixture.is_file():
                    raise SystemExit(f"missing fixture: {scenario.fixture}")
            print(json.dumps({"suite": args.suite, "scenarios": len(paths)}))
            return 0

    options = RunnerOptions(
        parent_route=args.parent_route,
        runs_override=args.runs,
        keep_workspace_on_failure=args.keep_workspace_on_failure,
        timeout_seconds=args.timeout_seconds,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.scenario:
        summary = asyncio.run(
            run_scenario(
                scenario_path,
                template_root=workspace_root,
                output_dir=args.output_dir.resolve(),
                options=options,
            )
        )
    else:
        summary = asyncio.run(
            run_suite(
                suite_dir,
                template_root=workspace_root,
                output_dir=args.output_dir.resolve(),
                options=options,
            )
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("pass_rate") == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

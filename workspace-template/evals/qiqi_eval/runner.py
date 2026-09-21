from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import time
from typing import Any

from .capture import repository_evidence, run_verification, runtime_evidence, work_item_evidence
from .fixture import FixtureManager
from .parent_driver import ParentAgentDriver
from .scenario import Scenario, load_scenario
from .scoring import score_run


@dataclass(frozen=True)
class RunnerOptions:
    parent_route: str = "codex-balanced"
    runs_override: int | None = None
    keep_workspace_on_failure: bool = False
    timeout_seconds: int = 3600


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-") or "scenario"


def _harness_commit(template_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(template_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _summary_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Eval: {result['scenario_id']} / run {result['run_index']}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Duration: {result['duration_ms']} ms",
    ]
    metrics = result.get("metrics", {})
    for key in ("waves", "attempts", "retries", "verification_count"):
        if key in metrics:
            lines.append(f"- {key}: {metrics[key]}")
    failures = result.get("failures", [])
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in failures)
    return "\n".join(lines) + "\n"


async def run_one(
    *,
    scenario: Scenario,
    run_index: int,
    template_root: Path,
    output_dir: Path,
    options: RunnerOptions,
) -> dict[str, Any]:
    manager = FixtureManager(template_root)
    workspace = manager.materialize(scenario.fixture)
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    parent_data: dict[str, Any]
    runtime_error: str | None = None
    try:
        try:
            parent = await asyncio.wait_for(
                ParentAgentDriver(route=options.parent_route).run(
                    workspace.root, scenario.prompt
                ),
                timeout=options.timeout_seconds,
            )
            parent_data = parent.to_dict()
        except Exception as exc:  # execution failures are eval evidence, not runner crashes
            parent_data = {
                "state": "runtime_error",
                "session_id": None,
                "response": None,
                "adapter": None,
                "route": options.parent_route,
                "blocker_type": None,
            }
            runtime_error = f"{type(exc).__name__}: {exc}"

        verification = [
            item.to_dict() for item in run_verification(workspace, scenario.expect.verification)
        ]
        evidence = {
            "parent": parent_data,
            "runtime_error": runtime_error,
            "repositories": repository_evidence(workspace),
            "runtime": runtime_evidence(workspace.root),
            "work_items": work_item_evidence(workspace.root),
            "verification": verification,
        }
        scored = score_run(scenario, evidence)
        if runtime_error:
            scored["status"] = "fail"
            scored["scores"]["runtime"] = False
            scored["failures"].insert(0, runtime_error)
        else:
            scored["scores"]["runtime"] = True

        duration_ms = int((time.monotonic() - started) * 1000)
        result = {
            "scenario_id": scenario.id,
            "run_index": run_index,
            "started_at": started_at,
            "duration_ms": duration_ms,
            "harness_commit": _harness_commit(template_root),
            **scored,
            "evidence": evidence,
        }
        run_dir = output_dir / _safe_name(scenario.id) / f"run-{run_index:03d}"
        _write_json(run_dir / "result.json", result)
        (run_dir / "summary.md").write_text(_summary_markdown(result), encoding="utf-8")
        if result["status"] == "fail" and options.keep_workspace_on_failure:
            retained = run_dir / "workspace"
            shutil.copytree(workspace.root, retained, dirs_exist_ok=False)
        return result
    finally:
        workspace.cleanup()


async def run_scenario(
    scenario_path: Path,
    *,
    template_root: Path,
    output_dir: Path,
    options: RunnerOptions,
) -> dict[str, Any]:
    scenario = load_scenario(scenario_path)
    runs = options.runs_override or scenario.runs
    results = []
    for index in range(1, runs + 1):
        results.append(
            await run_one(
                scenario=scenario,
                run_index=index,
                template_root=template_root,
                output_dir=output_dir,
                options=options,
            )
        )
    durations = [item["duration_ms"] for item in results]
    aggregate = {
        "scenario_id": scenario.id,
        "runs": len(results),
        "passes": sum(item["status"] == "pass" for item in results),
        "pass_rate": sum(item["status"] == "pass" for item in results) / len(results),
        "median_duration_ms": int(statistics.median(durations)) if durations else 0,
        "results": [
            {
                "run_index": item["run_index"],
                "status": item["status"],
                "duration_ms": item["duration_ms"],
                "metrics": item["metrics"],
                "failures": item["failures"],
            }
            for item in results
        ],
    }
    _write_json(output_dir / _safe_name(scenario.id) / "aggregate.json", aggregate)
    return aggregate


async def run_suite(
    suite_dir: Path,
    *,
    template_root: Path,
    output_dir: Path,
    options: RunnerOptions,
) -> dict[str, Any]:
    scenarios = sorted(suite_dir.glob("*.yaml"))
    if not scenarios:
        raise ValueError(f"suite has no YAML scenarios: {suite_dir}")
    aggregates = []
    for path in scenarios:
        aggregates.append(
            await run_scenario(
                path,
                template_root=template_root,
                output_dir=output_dir,
                options=options,
            )
        )
    total_runs = sum(item["runs"] for item in aggregates)
    total_passes = sum(item["passes"] for item in aggregates)
    summary = {
        "suite": suite_dir.name,
        "scenarios": len(aggregates),
        "runs": total_runs,
        "passes": total_passes,
        "pass_rate": (total_passes / total_runs) if total_runs else 0.0,
        "results": aggregates,
    }
    _write_json(output_dir / f"suite-{_safe_name(suite_dir.name)}.json", summary)
    return summary

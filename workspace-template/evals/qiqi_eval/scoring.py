from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .scenario import Scenario


def _graph_state(node_rows: list[dict[str, Any]]) -> str | None:
    active = [row for row in node_rows if int(row.get("active", 1)) == 1]
    if not active:
        return None
    if any(row.get("runtime_state") == "running" for row in active):
        return "running"
    if any(
        row.get("semantic_state") == "pending"
        and row.get("runtime_state") in {"settled", "failed", "blocked", "awaiting_review"}
        for row in active
    ):
        return "awaiting_review"
    if any(row.get("semantic_state") == "blocked" for row in active):
        return "blocked"
    if all(row.get("semantic_state") in {"satisfied", "cancelled"} for row in active):
        return "complete"
    if any(
        row.get("semantic_state") == "pending" and row.get("runtime_state") == "idle"
        for row in active
    ):
        return "ready"
    return "blocked"


def score_run(scenario: Scenario, evidence: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    scores: dict[str, bool] = {}

    parent = evidence.get("parent", {})
    parent_state = parent.get("state")
    expected_parent_states = {
        "success": {"settled"},
        "blocked": {"blocked"},
        "failure": {"failed"},
    }[scenario.expect.final_outcome]
    scores["final_outcome"] = parent_state in expected_parent_states
    if not scores["final_outcome"]:
        failures.append(
            f"parent outcome mismatch: expected {scenario.expect.final_outcome}, got {parent_state!r}"
        )

    repositories = evidence.get("repositories", {})
    touched = {
        name for name, item in repositories.items() if item.get("changed_files")
    }
    required = set(scenario.expect.touched_repositories.required)
    forbidden = set(scenario.expect.touched_repositories.forbidden)
    missing = sorted(required - touched)
    unexpected = sorted(forbidden & touched)
    scores["repo_selection"] = not missing and not unexpected
    if missing:
        failures.append(f"required repositories were not changed: {', '.join(missing)}")
    if unexpected:
        failures.append(f"forbidden repositories were changed: {', '.join(unexpected)}")

    verification = evidence.get("verification", [])
    failed_checks = [
        item for item in verification if item.get("returncode") != 0 or item.get("timed_out")
    ]
    scores["verification"] = not failed_checks
    for item in failed_checks:
        failures.append(
            f"verification failed for {item.get('repo')}: {item.get('command')} "
            f"(exit={item.get('returncode')})"
        )

    graph_expect = scenario.expect.graph
    attempts: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    if graph_expect is not None:
        tables = evidence.get("runtime", {}).get("tables", {})
        runs = tables.get("graph_runs", [])
        nodes = tables.get("graph_node_states", [])
        attempts = tables.get("graph_attempts", [])
        scores["graph_present"] = bool(runs and nodes)
        if not scores["graph_present"]:
            failures.append("expected TaskGraph evidence but no graph run was recorded")
        else:
            latest_run = max(runs, key=lambda row: int(row.get("updated_at_ns", 0)))
            run_id = latest_run.get("graph_run_id")
            run_nodes = [row for row in nodes if row.get("graph_run_id") == run_id]
            run_attempts = [row for row in attempts if row.get("graph_run_id") == run_id]
            derived_state = _graph_state(run_nodes)
            if graph_expect.final_state is not None:
                ok = derived_state == graph_expect.final_state
                scores["graph_final_state"] = ok
                if not ok:
                    failures.append(
                        f"graph final state mismatch: expected {graph_expect.final_state}, got {derived_state}"
                    )
            waves = len({row.get("wave_id") for row in run_attempts if row.get("wave_id")})
            if graph_expect.max_waves is not None:
                ok = waves <= graph_expect.max_waves
                scores["graph_wave_budget"] = ok
                if not ok:
                    failures.append(
                        f"graph wave budget exceeded: {waves} > {graph_expect.max_waves}"
                    )
            attempts_per_node = Counter(
                str(row.get("node_id")) for row in run_attempts if row.get("node_id") is not None
            )
            if graph_expect.max_attempts_per_node is not None:
                over = {
                    node: count
                    for node, count in attempts_per_node.items()
                    if count > graph_expect.max_attempts_per_node
                }
                scores["graph_attempt_budget"] = not over
                if over:
                    failures.append(
                        "graph attempt budget exceeded: "
                        + ", ".join(f"{node}={count}" for node, count in sorted(over.items()))
                    )
            if graph_expect.min_attempts_per_node is not None:
                active_nodes = [
                    str(row.get("node_id"))
                    for row in run_nodes
                    if int(row.get("active", 1)) == 1
                ]
                under = {
                    node: attempts_per_node.get(node, 0)
                    for node in active_nodes
                    if attempts_per_node.get(node, 0) < graph_expect.min_attempts_per_node
                }
                scores["graph_retry_floor"] = not under
                if under:
                    failures.append(
                        "graph retry floor not met: "
                        + ", ".join(f"{node}={count}" for node, count in sorted(under.items()))
                    )

    metrics: dict[str, Any] = {
        "touched_repositories": sorted(touched),
        "verification_count": len(verification),
    }
    if attempts:
        metrics["attempts"] = len(attempts)
        metrics["waves"] = len({row.get("wave_id") for row in attempts if row.get("wave_id")})
        by_node: defaultdict[str, int] = defaultdict(int)
        for row in attempts:
            by_node[str(row.get("node_id"))] += 1
        metrics["attempts_per_node"] = dict(sorted(by_node.items()))
        metrics["retries"] = sum(max(0, count - 1) for count in by_node.values())

    return {
        "status": "pass" if not failures else "fail",
        "scores": scores,
        "metrics": metrics,
        "failures": failures,
    }

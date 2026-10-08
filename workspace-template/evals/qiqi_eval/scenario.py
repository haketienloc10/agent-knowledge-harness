from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def _closed(data: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{label} has unsupported fields: {', '.join(unknown)}")


def _required_text(data: dict[str, Any], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _positive_int(value: Any, label: str, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True)
class VerificationCommand:
    repo: str
    command: str
    timeout_seconds: int = 60


@dataclass(frozen=True)
class GraphExpectation:
    final_state: str | None = None
    max_waves: int | None = None
    max_attempts_per_node: int | None = None
    min_attempts_per_node: int | None = None


@dataclass(frozen=True)
class TouchedRepositoriesExpectation:
    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioExpectation:
    final_outcome: str = "success"
    touched_repositories: TouchedRepositoriesExpectation = field(
        default_factory=TouchedRepositoriesExpectation
    )
    graph: GraphExpectation | None = None
    verification: tuple[VerificationCommand, ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    prompt: str
    fixture: Path
    description: str = ""
    runs: int = 1
    expect: ScenarioExpectation = field(default_factory=ScenarioExpectation)


def _parse_verification(value: Any) -> tuple[VerificationCommand, ...]:
    if value is None:
        return ()
    data = _mapping(value, "expect.verification")
    _closed(data, {"commands"}, "expect.verification")
    commands = data.get("commands", [])
    if not isinstance(commands, list):
        raise ValueError("expect.verification.commands must be a list")
    result: list[VerificationCommand] = []
    for index, raw in enumerate(commands):
        item = _mapping(raw, f"expect.verification.commands[{index}]")
        _closed(item, {"repo", "command", "timeout_seconds"}, f"expect.verification.commands[{index}]")
        result.append(
            VerificationCommand(
                repo=_required_text(item, "repo", f"expect.verification.commands[{index}]"),
                command=_required_text(item, "command", f"expect.verification.commands[{index}]"),
                timeout_seconds=_positive_int(
                    item.get("timeout_seconds"),
                    f"expect.verification.commands[{index}].timeout_seconds",
                    60,
                )
                or 60,
            )
        )
    return tuple(result)


def _parse_graph(value: Any) -> GraphExpectation | None:
    if value is None:
        return None
    data = _mapping(value, "expect.graph")
    _closed(
        data,
        {"final_state", "max_waves", "max_attempts_per_node", "min_attempts_per_node"},
        "expect.graph",
    )
    final_state = data.get("final_state")
    if final_state is not None and final_state not in {"ready", "running", "awaiting_review", "blocked", "complete"}:
        raise ValueError("expect.graph.final_state is invalid")
    return GraphExpectation(
        final_state=final_state,
        max_waves=_positive_int(data.get("max_waves"), "expect.graph.max_waves"),
        max_attempts_per_node=_positive_int(
            data.get("max_attempts_per_node"), "expect.graph.max_attempts_per_node"
        ),
        min_attempts_per_node=_positive_int(
            data.get("min_attempts_per_node"), "expect.graph.min_attempts_per_node"
        ),
    )


def _parse_expect(value: Any) -> ScenarioExpectation:
    if value is None:
        return ScenarioExpectation()
    data = _mapping(value, "expect")
    _closed(data, {"final_outcome", "touched_repositories", "graph", "verification"}, "expect")
    final_outcome = data.get("final_outcome", "success")
    if final_outcome not in {"success", "blocked", "failure"}:
        raise ValueError("expect.final_outcome must be success, blocked, or failure")

    touched_raw = data.get("touched_repositories", {})
    touched_data = _mapping(touched_raw, "expect.touched_repositories")
    _closed(touched_data, {"required", "forbidden"}, "expect.touched_repositories")
    touched = TouchedRepositoriesExpectation(
        required=_string_list(touched_data.get("required"), "expect.touched_repositories.required"),
        forbidden=_string_list(touched_data.get("forbidden"), "expect.touched_repositories.forbidden"),
    )
    overlap = sorted(set(touched.required) & set(touched.forbidden))
    if overlap:
        raise ValueError(
            "expect.touched_repositories cannot require and forbid the same repo: "
            + ", ".join(overlap)
        )

    return ScenarioExpectation(
        final_outcome=final_outcome,
        touched_repositories=touched,
        graph=_parse_graph(data.get("graph")),
        verification=_parse_verification(data.get("verification")),
    )


def load_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    data = _mapping(raw, str(path))
    _closed(data, {"id", "description", "prompt", "fixture", "runs", "expect"}, "scenario")
    fixture_value = _required_text(data, "fixture", "scenario")
    fixture = Path(fixture_value)
    if not fixture.is_absolute():
        fixture = (path.parent / fixture).resolve()
    runs = _positive_int(data.get("runs"), "scenario.runs", 1) or 1
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ValueError("scenario.description must be a string")
    return Scenario(
        id=_required_text(data, "id", "scenario"),
        description=description.strip(),
        prompt=_required_text(data, "prompt", "scenario"),
        fixture=fixture,
        runs=runs,
        expect=_parse_expect(data.get("expect")),
    )

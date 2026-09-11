#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


BASELINE_STARTUP = """`instructions/model-routing.md` **không phải mandatory startup read**. Default delegation route = `claude-balanced`.
Turn không delegate không hydrate route policy. Khi một turn thực sự cần delegation, đọc `instructions/model-routing.md` **just-in-time ngay trước route decision** để phân loại đúng fast/balanced/deep/verifier/Codex; không yêu cầu QiQi đoán exception signal từ always-on policy.
"""

CANDIDATE_STARTUP = """`instructions/model-routing.md` **không phải mandatory startup read**. Route-selection core luôn có trong always-on policy:

- `claude-fast`: task hẹp/cơ học, low uncertainty, expected outcome rõ và verification trực tiếp.
- `claude-balanced`: default cho ordinary implementation/refactor/test/docs/investigation khi không có stronger signal.
- `claude-deep`: high uncertainty/reasoning risk, architecture/design trade-off, migration nhiều ràng buộc hoặc blast radius đáng kể.
- `claude-verifier`: independent verification/review; **MUST START fresh by default** khi independence còn material.
- `codex-balanced`: Codex được user/project yêu cầu hoặc có verified capability reason cụ thể.
- Chọn route nhẹ nhất vẫn đủ tin cậy; không đổi route chỉ để né environment/dependency/permission blocker; exact route phải tồn tại trong `instructions/agent-routing.yaml`.

Turn không delegate không hydrate `instructions/model-routing.md`. Với ordinary delegation, chọn exact route trực tiếp từ core trên. Chỉ đọc `instructions/model-routing.md` khi extended rationale/edge-case guidance ngoài core thực sự material cho route decision; không hydrate như ceremony.
"""

BASELINE_BEFORE_DELEGATION = """4. Đọc `instructions/model-routing.md` ngay trước route decision rồi chọn exact route nhẹ nhất vẫn đủ tin cậy; `claude-balanced` là fallback/default khi policy không cho lý do rõ để chọn route khác.
"""

CANDIDATE_BEFORE_DELEGATION = """4. Chọn exact route nhẹ nhất vẫn đủ tin cậy từ always-on routing core; `claude-balanced` là fallback/default khi không có stronger signal. Chỉ hydrate `instructions/model-routing.md` nếu route decision cần extended rationale/edge-case guidance ngoài core; không tạo standalone read trên ordinary delegation path.
"""

BASELINE_ROUTING_ACTIVATION = """File này **không phải mandatory startup material**.

Always-on default invariant nằm ở `AGENTS.md`:

```text
Default delegation route = claude-balanced.
```

Turn không delegate **không đọc** file này chỉ để hoàn thành startup.

Khi một turn thực sự cần delegation, QiQi **đọc file này ngay trước route decision** rồi mới phân loại task vào fast/balanced/deep/verifier/Codex. Không yêu cầu always-on policy tự nhận diện trước các exception signal mà file này định nghĩa.

`claude-balanced` vẫn là deterministic default/fallback khi sau khi áp dụng policy không có lý do rõ để chọn route khác. User/project explicit route selection vẫn phải được kiểm tra theo policy và route registry trước delegation.

Mục tiêu của activation rule là tránh fixed context tax cho status-only/answer-only
turn nhưng không đánh đổi route-selection correctness ở các turn thực sự delegate.
"""

CANDIDATE_ROUTING_ACTIVATION = """File này **không phải mandatory startup material** và **không phải required standalone read trước ordinary delegation**.

Always-on routing core trong `AGENTS.md` sở hữu common-path classification cho `claude-fast`, `claude-balanced`, `claude-deep`, `claude-verifier` và `codex-balanced`, gồm deterministic `claude-balanced` fallback cùng verifier fresh-START invariant.

Turn không delegate **không đọc** file này chỉ để hoàn thành startup. Ordinary delegation chọn exact route trực tiếp từ always-on core, không hydrate file này như ceremony.

Chỉ đọc file này khi extended rationale/edge-case guidance ngoài always-on core thực sự material cho route decision. User/project explicit route selection vẫn phải được kiểm tra theo policy và route registry trước delegation.

Mục tiêu của activation rule là tránh cả fixed startup tax lẫn standalone parent-inference boundary trên common delegation path mà không đánh đổi route-selection correctness.
"""


def _swap_once(text: str, old: str, new: str, *, label: str) -> tuple[str, bool]:
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == 1 and new_count == 0:
        return text.replace(old, new, 1), True
    if old_count == 0 and new_count == 1:
        return text, False
    raise RuntimeError(
        f"{label}: expected exactly one baseline block or one candidate block; "
        f"found baseline={old_count}, candidate={new_count}. Refusing ambiguous mutation."
    )


def to_candidate(agents: str, routing: str) -> tuple[str, str, bool]:
    agents, changed_startup = _swap_once(
        agents, BASELINE_STARTUP, CANDIDATE_STARTUP, label="AGENTS startup"
    )
    agents, changed_before = _swap_once(
        agents,
        BASELINE_BEFORE_DELEGATION,
        CANDIDATE_BEFORE_DELEGATION,
        label="AGENTS before-delegation",
    )
    routing, changed_routing = _swap_once(
        routing,
        BASELINE_ROUTING_ACTIVATION,
        CANDIDATE_ROUTING_ACTIVATION,
        label="model-routing activation",
    )
    changed = changed_startup or changed_before or changed_routing
    if len({changed_startup, changed_before, changed_routing}) != 1:
        raise RuntimeError("workspace is mixed baseline/candidate; refusing partial mutation")
    return agents, routing, changed


def to_baseline(agents: str, routing: str) -> tuple[str, str, bool]:
    agents, changed_startup = _swap_once(
        agents, CANDIDATE_STARTUP, BASELINE_STARTUP, label="AGENTS startup"
    )
    agents, changed_before = _swap_once(
        agents,
        CANDIDATE_BEFORE_DELEGATION,
        BASELINE_BEFORE_DELEGATION,
        label="AGENTS before-delegation",
    )
    routing, changed_routing = _swap_once(
        routing,
        CANDIDATE_ROUTING_ACTIVATION,
        BASELINE_ROUTING_ACTIVATION,
        label="model-routing activation",
    )
    changed = changed_startup or changed_before or changed_routing
    if len({changed_startup, changed_before, changed_routing}) != 1:
        raise RuntimeError("workspace is mixed baseline/candidate; refusing partial mutation")
    return agents, routing, changed


def detect_state(agents: str, routing: str) -> str:
    baseline = (
        BASELINE_STARTUP in agents
        and BASELINE_BEFORE_DELEGATION in agents
        and BASELINE_ROUTING_ACTIVATION in routing
    )
    candidate = (
        CANDIDATE_STARTUP in agents
        and CANDIDATE_BEFORE_DELEGATION in agents
        and CANDIDATE_ROUTING_ACTIVATION in routing
    )
    if baseline and not candidate:
        return "baseline"
    if candidate and not baseline:
        return "candidate"
    return "mixed-or-unknown"


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_name(f".{path.name}.issue49.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Switch one QiQi workspace between issue #49 routing A/B policy states."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("baseline", "candidate", "check"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.workspace.resolve()
    agents_path = root / "AGENTS.md"
    routing_path = root / "instructions" / "model-routing.md"
    if not agents_path.is_file() or not routing_path.is_file():
        raise SystemExit(
            f"workspace must contain AGENTS.md and instructions/model-routing.md: {root}"
        )

    agents = agents_path.read_text(encoding="utf-8")
    routing = routing_path.read_text(encoding="utf-8")
    before = detect_state(agents, routing)

    if args.mode == "check":
        print(before)
        return 0 if before in {"baseline", "candidate"} else 2

    if args.mode == "candidate":
        next_agents, next_routing, changed = to_candidate(agents, routing)
    else:
        next_agents, next_routing, changed = to_baseline(agents, routing)

    after = detect_state(next_agents, next_routing)
    if after != args.mode:
        raise RuntimeError(f"transform did not reach requested state: {after}")

    print(f"{before} -> {after}{' (dry-run)' if args.dry_run else ''}")
    if not args.dry_run and changed:
        _atomic_write(agents_path, next_agents)
        _atomic_write(routing_path, next_routing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

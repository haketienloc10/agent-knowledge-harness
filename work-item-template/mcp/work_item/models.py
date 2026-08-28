from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkItemStatus = Literal["active", "waiting", "blocked", "done", "cancelled"]
RepoStatus = Literal["pending", "active", "waiting", "blocked", "done", "not_required"]
QuestionStatus = Literal["open", "resolved"]
DecisionStatus = Literal["active", "superseded"]
ChangeType = Literal[
    "requirement_added",
    "requirement_changed",
    "requirement_removed",
    "scope_changed",
]
ChangeStatus = Literal["proposed", "accepted", "rejected", "superseded"]
BlockerStatus = Literal["open", "resolved"]
HandoffStatus = Literal["pending", "resolved"]


class _SemanticRecord(BaseModel):
    """Typed canonical fields plus open provenance/evidence extensions."""

    model_config = ConfigDict(extra="allow")


class QuestionPatch(_SemanticRecord):
    id: str = Field(description="Stable question id within the Work Item, for example q1.")
    question: str = Field(
        description=(
            "The external/product ambiguity that needs resolution. Use `question`, not `text`, "
            "and do not encode status markers such as '[open]' into this string."
        )
    )
    status: QuestionStatus | None = Field(
        default=None,
        description="Question lifecycle when recorded: open or resolved.",
    )
    answer: str | None = Field(
        default=None,
        description="Resolved answer when known. Core enforces resolved-question invariants.",
    )
    decision_id: str | None = Field(
        default=None,
        description="Decision id that resolves this question when resolution is captured as a decision.",
    )


class DecisionPatch(_SemanticRecord):
    id: str = Field(description="Stable decision id within the Work Item, for example d1.")
    summary: str = Field(
        description="Material decision that explains current task requirements or behavior."
    )
    status: DecisionStatus | None = Field(
        default=None,
        description="Decision lifecycle: active or superseded.",
    )
    superseded_by: str | None = Field(
        default=None,
        description="Replacement decision id when status is superseded.",
    )


class RequirementChangePatch(_SemanticRecord):
    id: str = Field(description="Stable requirement/scope change id, for example c1.")
    type: ChangeType = Field(
        description=(
            "Requirement/scope evolution type only. Do not use this record for implementation "
            "progress, generic code changes, investigation notes, or activity logs."
        )
    )
    status: ChangeStatus = Field(
        description="Change lifecycle: proposed, accepted, rejected, or superseded."
    )
    summary: str = Field(description="What requirement or scope changed and how.")


class RepoPatch(_SemanticRecord):
    status: RepoStatus | None = Field(
        default=None,
        description="State of this repository's task contribution, not the overall Work Item status.",
    )
    summary: str | None = Field(
        default=None,
        description=(
            "Current effective repository contribution/state after all work known so far. This snapshot "
            "is not a narrative of the latest session. Describe what is true now, including implemented "
            "outcome, verified boundary, and remaining repo work when material. Do not replace this "
            "snapshot with a narrative of the latest investigation, review, report, command sequence, "
            "or agent session; historical phase findings belong in checkpoints or optional artifacts."
        ),
    )
    verification: list[str] | None = Field(
        default=None,
        description="Concrete verification evidence established for this repository.",
    )


class BlockerPatch(_SemanticRecord):
    id: str = Field(description="Stable blocker id within the Work Item, for example b1.")
    status: BlockerStatus = Field(description="Blocker lifecycle: open or resolved.")
    summary: str = Field(
        description="Condition materially preventing progress; not generic risks or notes."
    )


class HandoffPatch(_SemanticRecord):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(description="Stable handoff id within the Work Item, for example h1.")
    from_: str = Field(
        alias="from",
        description="Repository/owner that discovered or is handing off the remaining work.",
    )
    to: str = Field(description="Repository/owner that should receive the remaining work.")
    status: HandoffStatus = Field(description="Handoff lifecycle: pending or resolved.")
    summary: str = Field(description="Remaining cross-repo/owner work being handed off.")


class NextActionPatch(_SemanticRecord):
    action: str = Field(description="Concrete next action to perform.")
    repo: str | None = Field(
        default=None,
        description="Repository responsible for the action when repo-owned.",
    )
    owner: str | None = Field(
        default=None,
        description="Non-repository owner responsible for the action when applicable.",
    )

    @model_validator(mode="after")
    def _require_target(self) -> "NextActionPatch":
        if self.repo is None and self.owner is None:
            raise ValueError("next action must identify either repo or owner")
        return self


class CheckpointPatch(_SemanticRecord):
    summary: str = Field(
        description=(
            "Material milestone/evidence summary established by a substantive phase; not terminal "
            "logs, commands, or routine progress bookkeeping. Keep enough material history for a "
            "future reader to reconstruct major task progress without opening optional artifacts."
        )
    )
    repo: str | None = Field(
        default=None,
        description="Repository this checkpoint belongs to when repo-specific; use global when appropriate.",
    )
    kind: str | None = Field(
        default=None,
        description=(
            "Optional free-form descriptive phase/milestone label such as investigation, implementation, "
            "verification, review, decision, report, or completion. This is not an enum or workflow FSM."
        ),
    )
    artifact_id: str | None = Field(
        default=None,
        description=(
            "Optional artifact id containing detailed material for this milestone, for example review:1 "
            "or report:1. Omit when the phase has no artifact."
        ),
    )
    at: str | None = Field(
        default=None,
        description="Optional recorded timestamp/provenance string when already known.",
    )


class WorkItemPatch(BaseModel):
    """Agent-facing typed JSON merge-patch for canonical Work Item state."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None,
        description="Current human-readable task title.",
    )
    status: WorkItemStatus | None = Field(
        default=None,
        description=(
            "Overall Work Item lifecycle status. This is global task state, not a repository status; "
            "QiQi conventionally owns it."
        ),
    )
    phase: str | None = Field(
        default=None,
        description="Free-form descriptive current phase. It is not an enum and not a transition FSM.",
    )
    summary: str | None = Field(
        default=None,
        description=(
            "Concise current task snapshot for continuation. Do not put long investigation, plan, "
            "review, or report content here; use optional artifacts for that detail."
        ),
    )
    current_requirements: list[str] | None = Field(
        default=None,
        description=(
            "Full replacement of the effective requirements that are true now, not original intake "
            "history. Arrays replace atomically."
        ),
    )
    questions: list[QuestionPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of material external/product ambiguities; not free-form notes or strings. "
            "Each record requires id and question; arrays replace atomically."
        ),
    )
    decisions: list[DecisionPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of material decisions explaining current requirements/state, not generic "
            "observations or next actions. Arrays replace atomically."
        ),
    )
    changes: list[RequirementChangePatch] | None = Field(
        default=None,
        description=(
            "Full replacement of requirement/scope evolution history only. Do not record generic code "
            "changes or progress here. Arrays replace atomically."
        ),
    )
    repos: dict[str, RepoPatch | None] | None = Field(
        default=None,
        description=(
            "Repository map keyed by repo name. Each repo summary is the current effective repo truth, "
            "not a narrative of the latest session. Nested repo objects merge; only supplied repo "
            "fields are patched. A repo value of null requests deletion through JSON merge-patch semantics."
        ),
    )
    blockers: list[BlockerPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of conditions materially blocking progress; not generic risks or notes. "
            "Arrays replace atomically."
        ),
    )
    handoffs: list[HandoffPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of explicit remaining-work transfers between repositories/owners. "
            "Arrays replace atomically."
        ),
    )
    next_actions: list[NextActionPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of concrete next actions. Each item is an object with action and repo "
            "or owner; do not send plain strings. Arrays replace atomically."
        ),
    )
    checkpoints: list[CheckpointPatch] | None = Field(
        default=None,
        description=(
            "Full replacement of accumulated material phase/milestone history. Preserve existing material "
            "checkpoints and append one when the current substantive session establishes a new milestone. "
            "Use optional kind/artifact_id to make major progress reconstructable; do not record terminal "
            "logs or routine activity. Arrays replace atomically."
        ),
    )

    def to_merge_patch(self) -> dict[str, Any]:
        """Preserve explicit null while omitting fields the caller did not provide."""

        return self.model_dump(exclude_unset=True, by_alias=True, mode="python")

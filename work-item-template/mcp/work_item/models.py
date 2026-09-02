from __future__ import annotations

from typing import Annotated, Any, Literal

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
HistoryCollection = Literal[
    "questions", "decisions", "changes", "checkpoints", "blockers", "handoffs"
]
HistoryStatus = Literal[
    "open", "resolved", "active", "superseded", "proposed", "accepted", "rejected", "pending"
]
MUTATION_OPERATION_MAX = 50


class _SemanticRecord(BaseModel):
    """Canonical semantic record with open provenance/evidence extensions."""

    model_config = ConfigDict(extra="allow")


class QuestionRecord(_SemanticRecord):
    id: str = Field(description="Stable question id within the Work Item, for example q1.")
    question: str = Field(
        description=(
            "The external/product ambiguity that needs resolution. Use `question`, not `text`, "
            "and do not encode status markers such as '[open]' into this string."
        )
    )
    status: QuestionStatus = Field(
        description="Required canonical question lifecycle: open or resolved."
    )
    answer: str | None = Field(default=None, description="Resolved answer when known.")
    decision_id: str | None = Field(
        default=None,
        description="Decision id that resolves this question when resolution is captured as a decision.",
    )

    @model_validator(mode="after")
    def _resolved_question_has_resolution(self) -> "QuestionRecord":
        if self.status == "resolved" and not (
            isinstance(self.answer, str) and self.answer.strip()
        ) and not (
            isinstance(self.decision_id, str) and self.decision_id.strip()
        ):
            raise ValueError("resolved question requires answer or decision_id")
        return self


class DecisionRecord(_SemanticRecord):
    id: str = Field(description="Stable decision id within the Work Item, for example d1.")
    summary: str = Field(
        description="Material decision that explains current task requirements or behavior."
    )
    status: DecisionStatus = Field(
        description="Required canonical decision lifecycle: active or superseded."
    )
    superseded_by: str | None = Field(
        default=None,
        description="Replacement decision id when status is superseded.",
    )

    @model_validator(mode="after")
    def _superseded_decision_has_successor(self) -> "DecisionRecord":
        if self.status == "superseded" and not (
            isinstance(self.superseded_by, str) and self.superseded_by.strip()
        ):
            raise ValueError("superseded decision requires superseded_by")
        return self


class RequirementChangeRecord(_SemanticRecord):
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


class BlockerRecord(_SemanticRecord):
    id: str = Field(description="Stable blocker id within the Work Item, for example b1.")
    status: BlockerStatus = Field(description="Blocker lifecycle: open or resolved.")
    summary: str = Field(
        description="Condition materially preventing progress; not generic risks or notes."
    )


class HandoffRecord(_SemanticRecord):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(description="Stable handoff id within the Work Item, for example h1.")
    from_: str = Field(
        alias="from",
        description="Repository/owner that discovered or is handing off the remaining work.",
    )
    to: str = Field(description="Repository/owner that should receive the remaining work.")
    status: HandoffStatus = Field(description="Handoff lifecycle: pending or resolved.")
    summary: str = Field(description="Remaining cross-repo/owner work being handed off.")


class NextActionRecord(_SemanticRecord):
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
    def _require_target(self) -> "NextActionRecord":
        if self.repo is None and self.owner is None:
            raise ValueError("next action must identify either repo or owner")
        return self


class CheckpointRecord(_SemanticRecord):
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


class RepoPatch(_SemanticRecord):
    """Partial nested current-repository mutation."""

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


HistoryRecord = (
    QuestionRecord
    | DecisionRecord
    | RequirementChangeRecord
    | CheckpointRecord
    | BlockerRecord
    | HandoffRecord
)


class HistoryCollectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    current: int | None = Field(default=None, ge=0)
    hidden: int | None = Field(default=None, ge=0)


class WorkItemSnapshot(BaseModel):
    """Bounded current-state projection returned by work_item_get."""

    model_config = ConfigDict(extra="forbid")

    id: str
    revision: int = Field(ge=1)
    created_at: str
    updated_at: str
    title: str
    status: WorkItemStatus
    phase: str
    summary: str
    current_requirements: list[str]
    repos: dict[str, dict[str, Any]]
    open_questions: list[QuestionRecord]
    active_decisions: list[DecisionRecord]
    open_blockers: list[BlockerRecord]
    pending_handoffs: list[HandoffRecord]
    next_actions: list[NextActionRecord]
    history: dict[str, HistoryCollectionSummary]
    artifacts: list[dict[str, Any]] = Field(default_factory=list)


class WorkItemHistoryPage(BaseModel):
    """One revision-bound page from exactly one canonical historical collection."""

    model_config = ConfigDict(extra="forbid")

    id: str
    revision: int = Field(ge=1)
    collection: HistoryCollection
    status: HistoryStatus | None = None
    repository: str | None = None
    items: list[HistoryRecord]
    returned: int = Field(ge=0)
    total: int = Field(ge=0)
    next_cursor: str | None = None


class WorkItemStatePatch(BaseModel):
    """Patch only the bounded current-state portion of a canonical Work Item."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, description="Current human-readable task title.")
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
            "history. This bounded current-state array replaces atomically."
        ),
    )
    repos: dict[str, RepoPatch | None] | None = Field(
        default=None,
        description=(
            "Repository map keyed by repo name. Nested repo objects merge by supplied fields; each repo "
            "summary remains current effective repo truth. A repo value of null explicitly removes that "
            "repository entry through JSON merge-patch semantics."
        ),
    )
    next_actions: list[NextActionRecord] | None = Field(
        default=None,
        description=(
            "Full replacement of concrete current next actions. This is bounded current state rather than "
            "history; each item has action plus repo or owner."
        ),
    )

    def to_merge_patch(self) -> dict[str, Any]:
        """Preserve explicit null while omitting fields the caller did not provide."""
        return self.model_dump(exclude_unset=True, by_alias=True, mode="python")


class _RecordMutation(BaseModel):
    """Partial semantic command for one stable-id canonical record."""

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> "_RecordMutation":
        for field_name in self.model_fields_set:
            if field_name in self.__class__.model_fields and getattr(self, field_name) is None:
                raise ValueError(
                    f"{field_name} cannot be null in an incremental semantic mutation; omit it instead"
                )
        for key, value in (self.__pydantic_extra__ or {}).items():
            if value is None:
                raise ValueError(
                    f"{key} cannot be null in an incremental semantic mutation; omit it instead"
                )
        return self


class QuestionMutation(_RecordMutation):
    id: str = Field(description="Stable question id to create or advance.")
    question: str | None = Field(
        default=None,
        description="Required on create; immutable once the question id exists.",
    )
    status: QuestionStatus | None = Field(
        default=None,
        description="Create lifecycle or monotonic transition; resolved cannot return to open.",
    )
    answer: str | None = Field(
        default=None,
        description="Write-once resolution answer; resolving requires answer or decision_id.",
    )
    decision_id: str | None = Field(
        default=None,
        description="Write-once resolving decision reference validated against the final candidate document.",
    )


class DecisionMutation(_RecordMutation):
    id: str = Field(description="Stable decision id to create or advance.")
    summary: str | None = Field(
        default=None,
        description="Required on create; immutable once the decision id exists.",
    )
    status: DecisionStatus | None = Field(
        default=None,
        description="Create lifecycle or monotonic transition; superseded cannot return to active.",
    )
    superseded_by: str | None = Field(
        default=None,
        description="Write-once replacement decision id when superseding this decision.",
    )


class RequirementChangeMutation(_RecordMutation):
    id: str = Field(description="Stable requirement/scope change id to create or advance.")
    type: ChangeType | None = Field(
        default=None,
        description="Required on create and immutable once this change id exists.",
    )
    status: ChangeStatus | None = Field(
        default=None,
        description=(
            "Controlled lifecycle transition: proposed may become accepted/rejected/superseded; "
            "accepted may become superseded; terminal states do not reopen."
        ),
    )
    summary: str | None = Field(
        default=None,
        description="Required on create and immutable once this change id exists.",
    )


class BlockerMutation(_RecordMutation):
    id: str = Field(description="Stable blocker id to create or advance.")
    status: BlockerStatus | None = Field(
        default=None,
        description="Create lifecycle or monotonic transition; resolved cannot reopen.",
    )
    summary: str | None = Field(
        default=None,
        description="Required on create and immutable once this blocker id exists.",
    )


class HandoffMutation(_RecordMutation):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(description="Stable handoff id to create or advance.")
    from_: str | None = Field(
        default=None,
        alias="from",
        description="Required on create and immutable once this handoff id exists.",
    )
    to: str | None = Field(
        default=None,
        description="Required on create and immutable once this handoff id exists.",
    )
    status: HandoffStatus | None = Field(
        default=None,
        description="Create lifecycle or monotonic transition; resolved cannot become pending.",
    )
    summary: str | None = Field(
        default=None,
        description="Required on create and immutable once this handoff id exists.",
    )


class CheckpointAppendOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["checkpoint_append"]
    value: CheckpointRecord = Field(
        description="One new material milestone appended to canonical checkpoint history."
    )


class QuestionUpsertOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["question_upsert"]
    value: QuestionMutation


class DecisionUpsertOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["decision_upsert"]
    value: DecisionMutation


class ChangeUpsertOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["change_upsert"]
    value: RequirementChangeMutation


class BlockerUpsertOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["blocker_upsert"]
    value: BlockerMutation


class HandoffUpsertOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["handoff_upsert"]
    value: HandoffMutation


WorkItemOperation = Annotated[
    CheckpointAppendOperation
    | QuestionUpsertOperation
    | DecisionUpsertOperation
    | ChangeUpsertOperation
    | BlockerUpsertOperation
    | HandoffUpsertOperation,
    Field(discriminator="op"),
]


class WorkItemMutation(BaseModel):
    """Atomic current-state patch plus typed incremental semantic operations."""

    model_config = ConfigDict(extra="forbid")

    state: WorkItemStatePatch | None = Field(
        default=None,
        description=(
            "Current effective state patch only: title/status/phase/summary/current_requirements/repos/"
            "next_actions. Historical semantic collections are intentionally not replaceable here."
        ),
    )
    operations: list[WorkItemOperation] = Field(
        default_factory=list,
        max_length=MUTATION_OPERATION_MAX,
        description=(
            "Up to 50 typed semantic operations applied in caller order and committed atomically under "
            "one exact whole Work Item revision."
        ),
    )

    @model_validator(mode="after")
    def _require_material_mutation(self) -> "WorkItemMutation":
        state_patch = self.state.to_merge_patch() if self.state is not None else {}
        if not state_patch and not self.operations:
            raise ValueError("mutation must contain a non-empty state patch or at least one operation")
        return self

    def to_core_mutation(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.state is not None:
            state_patch = self.state.to_merge_patch()
            if state_patch:
                result["state"] = state_patch
        if self.operations:
            result["operations"] = [
                operation.model_dump(mode="python", by_alias=True, exclude_none=True)
                for operation in self.operations
            ]
        return result

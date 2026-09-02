from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from core import (
    ConflictError,
    NotFoundError,
    ValidationError,
    _connect,
    _merge_patch,
    _now_iso,
    _required_text,
    validate_document,
)

MUTATION_OPERATION_MAX = 50
STATE_FIELDS = {
    "title",
    "status",
    "phase",
    "summary",
    "current_requirements",
    "repos",
    "next_actions",
}
OPERATION_COLLECTION = {
    "question_upsert": "questions",
    "decision_upsert": "decisions",
    "change_upsert": "changes",
    "blocker_upsert": "blockers",
    "handoff_upsert": "handoffs",
}
LIFECYCLE_TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "questions": {
        "open": {"open", "resolved"},
        "resolved": {"resolved"},
    },
    "decisions": {
        "active": {"active", "superseded"},
        "superseded": {"superseded"},
    },
    "changes": {
        "proposed": {"proposed", "accepted", "rejected", "superseded"},
        "accepted": {"accepted", "superseded"},
        "rejected": {"rejected"},
        "superseded": {"superseded"},
    },
    "blockers": {
        "open": {"open", "resolved"},
        "resolved": {"resolved"},
    },
    "handoffs": {
        "pending": {"pending", "resolved"},
        "resolved": {"resolved"},
    },
}
IMMUTABLE_FIELDS = {
    "questions": {"question"},
    "decisions": {"summary"},
    "changes": {"type", "summary"},
    "blockers": {"summary"},
    "handoffs": {"from", "to", "summary"},
}
WRITE_ONCE_FIELDS = {
    "questions": {"answer", "decision_id"},
    "decisions": {"superseded_by"},
    "changes": set(),
    "blockers": set(),
    "handoffs": set(),
}


def _append_changed(changed: list[str], label: str) -> None:
    if label not in changed:
        changed.append(label)


def _validate_mutation_envelope(mutation: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(mutation, dict):
        raise ValidationError("mutation must be an object")
    unknown = sorted(set(mutation) - {"state", "operations"})
    if unknown:
        raise ValidationError("mutation contains unknown fields: " + ", ".join(unknown))

    state = mutation.get("state", {})
    operations = mutation.get("operations", [])
    if state is None:
        state = {}
    if operations is None:
        operations = []
    if not isinstance(state, dict):
        raise ValidationError("mutation.state must be an object")
    if not isinstance(operations, list):
        raise ValidationError("mutation.operations must be a list")
    if len(operations) > MUTATION_OPERATION_MAX:
        raise ValidationError(
            f"mutation.operations must contain at most {MUTATION_OPERATION_MAX} operations"
        )
    if not state and not operations:
        raise ValidationError("mutation must change current state or contain semantic operations")

    unknown_state = sorted(set(state) - STATE_FIELDS)
    if unknown_state:
        raise ValidationError(
            "mutation.state may only change bounded current-state fields; unsupported: "
            + ", ".join(unknown_state)
        )
    return state, operations


def _apply_state_patch(
    current: dict[str, Any], state: dict[str, Any], changed: list[str]
) -> dict[str, Any]:
    if not state:
        return copy.deepcopy(current)
    candidate = _merge_patch(current, state)
    for field in state:
        if field != "repos":
            if candidate.get(field) != current.get(field):
                _append_changed(changed, field)
            continue

        repos_patch = state.get("repos")
        if not isinstance(repos_patch, dict):
            # Final canonical validation will also reject an invalid repos shape, but this
            # keeps changed-label calculation deterministic and actionable.
            raise ValidationError("mutation.state.repos must be an object")
        current_repos = current.get("repos", {})
        candidate_repos = candidate.get("repos", {})
        for repo in repos_patch:
            if candidate_repos.get(repo) != current_repos.get(repo) or (
                repo in current_repos and repo not in candidate_repos
            ):
                _append_changed(changed, f"repos.{repo}")
    return candidate


def _find_record(items: list[Any], record_id: str) -> tuple[int | None, dict[str, Any] | None]:
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == record_id:
            return index, item
    return None, None


def _apply_upsert(
    document: dict[str, Any],
    collection: str,
    value: Any,
    *,
    op_name: str,
    changed: list[str],
) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{op_name}.value must be an object")
    record_id = _required_text(value.get("id"), f"{op_name}.value.id", max_chars=128)
    items = document.get(collection)
    if not isinstance(items, list):
        raise ValidationError(f"canonical {collection} must be a list")

    index, existing = _find_record(items, record_id)
    if existing is None:
        items.append(copy.deepcopy(value))
        _append_changed(changed, f"{collection}:{record_id}")
        return

    result = copy.deepcopy(existing)
    old_status = existing.get("status")
    new_status = value.get("status", old_status)
    transitions = LIFECYCLE_TRANSITIONS[collection]
    if old_status not in transitions:
        raise ValidationError(
            f"canonical {collection}:{record_id} has unsupported lifecycle status {old_status!r}"
        )
    if new_status not in transitions[old_status]:
        raise ValidationError(
            f"{op_name} cannot transition {collection}:{record_id} from {old_status} to {new_status}"
        )

    immutable = IMMUTABLE_FIELDS[collection]
    write_once = WRITE_ONCE_FIELDS[collection]
    for key, incoming in value.items():
        if key == "id":
            if incoming != record_id:
                raise ValidationError(f"{op_name} cannot change record id")
            continue
        if key in immutable:
            if key in existing and existing[key] != incoming:
                raise ValidationError(
                    f"{op_name} cannot rewrite immutable {collection}:{record_id}.{key}"
                )
            result[key] = copy.deepcopy(incoming)
            continue
        if key == "status":
            result[key] = incoming
            continue
        if key in write_once:
            if key in existing and existing[key] is not None and existing[key] != incoming:
                raise ValidationError(
                    f"{op_name} cannot rewrite write-once {collection}:{record_id}.{key}"
                )
            result[key] = copy.deepcopy(incoming)
            continue

        # Open provenance/evidence extensions remain additive. Existing evidence is not
        # silently rewritten by an incremental lifecycle command.
        if key in existing and existing[key] != incoming:
            raise ValidationError(
                f"{op_name} cannot rewrite existing provenance field {collection}:{record_id}.{key}"
            )
        result[key] = copy.deepcopy(incoming)

    if collection == "questions":
        supplied_resolution = "answer" in value or "decision_id" in value
        if supplied_resolution and result.get("status") != "resolved":
            raise ValidationError(
                f"question_upsert must transition questions:{record_id} to resolved when adding resolution"
            )
    elif collection == "decisions":
        if "superseded_by" in value and result.get("status") != "superseded":
            raise ValidationError(
                f"decision_upsert must transition decisions:{record_id} to superseded when setting superseded_by"
            )

    if result != existing:
        assert index is not None
        items[index] = result
        _append_changed(changed, f"{collection}:{record_id}")


def _apply_checkpoint_append(
    document: dict[str, Any], value: Any, changed: list[str]
) -> None:
    if not isinstance(value, dict):
        raise ValidationError("checkpoint_append.value must be an object")
    if "id" in value:
        raise ValidationError("checkpoint_append does not use stable checkpoint ids")
    checkpoints = document.get("checkpoints")
    if not isinstance(checkpoints, list):
        raise ValidationError("canonical checkpoints must be a list")
    checkpoints.append(copy.deepcopy(value))
    _append_changed(changed, "checkpoints")


def _apply_operations(
    document: dict[str, Any], operations: list[dict[str, Any]], changed: list[str]
) -> None:
    seen_targets: set[tuple[str, str]] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValidationError(f"mutation.operations[{index}] must be an object")
        if set(operation) != {"op", "value"}:
            raise ValidationError(
                f"mutation.operations[{index}] must contain exactly op and value"
            )
        op_name = operation.get("op")
        value = operation.get("value")
        if op_name == "checkpoint_append":
            _apply_checkpoint_append(document, value, changed)
            continue
        if op_name not in OPERATION_COLLECTION:
            raise ValidationError(f"unsupported semantic operation: {op_name!r}")
        if not isinstance(value, dict):
            raise ValidationError(f"{op_name}.value must be an object")
        record_id = _required_text(
            value.get("id"), f"mutation.operations[{index}].value.id", max_chars=128
        )
        collection = OPERATION_COLLECTION[op_name]
        target = (collection, record_id)
        if target in seen_targets:
            raise ValidationError(
                f"mutation contains duplicate target {collection}:{record_id}; use one deterministic operation per record"
            )
        seen_targets.add(target)
        _apply_upsert(
            document,
            collection,
            value,
            op_name=op_name,
            changed=changed,
        )


def _validate_cross_record_references(document: dict[str, Any]) -> None:
    decisions = document.get("decisions", [])
    decision_ids = {
        item.get("id")
        for item in decisions
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for question in document.get("questions", []):
        if not isinstance(question, dict):
            continue
        decision_id = question.get("decision_id")
        if decision_id is not None and decision_id not in decision_ids:
            raise ValidationError(
                f"question {question.get('id')!r} references missing decision_id {decision_id!r}"
            )
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get("status") != "superseded":
            continue
        decision_id = decision.get("id")
        successor = decision.get("superseded_by")
        if successor == decision_id:
            raise ValidationError(f"decision {decision_id!r} cannot supersede itself")
        if successor not in decision_ids:
            raise ValidationError(
                f"decision {decision_id!r} references missing superseded_by {successor!r}"
            )


def mutate_work_item(
    db_path: str | Path,
    item_id: str,
    expected_revision: int,
    mutation: dict[str, Any],
) -> dict[str, Any]:
    """Apply one bounded state patch plus typed semantic operations atomically.

    The canonical persistence model remains one document and one optimistic revision. No
    stale semantic operation is automatically rebased: a caller must reread/reconcile and
    retry against the exact latest revision.
    """
    item_id = _required_text(item_id, "id", max_chars=256)
    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 1
    ):
        raise ValidationError("expected_revision must be a positive integer")
    state, operations = _validate_mutation_envelope(mutation)

    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"work item not found: {item_id}")
        if row["revision"] != expected_revision:
            raise ConflictError(
                f"revision conflict for {item_id}: expected {expected_revision}, current {row['revision']}"
            )

        current = json.loads(row["document_json"])
        current = validate_document(current)
        changed: list[str] = []
        candidate = _apply_state_patch(current, state, changed)
        _apply_operations(candidate, operations, changed)
        candidate["id"] = item_id
        candidate = validate_document(candidate)
        _validate_cross_record_references(candidate)

        if not changed or candidate == current:
            raise ValidationError("mutation does not change canonical Work Item state")

        now = _now_iso()
        new_revision = expected_revision + 1
        encoded = json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        db_cursor = conn.execute(
            """
            UPDATE work_items
            SET revision = ?, status = ?, document_json = ?, updated_at = ?
            WHERE id = ? AND revision = ?
            """,
            (
                new_revision,
                candidate["status"],
                encoded,
                now,
                item_id,
                expected_revision,
            ),
        )
        if db_cursor.rowcount != 1:
            raise ConflictError(f"revision conflict for {item_id}; reread before retrying")
        conn.execute("COMMIT")
        return {
            "updated": True,
            "id": item_id,
            "revision": new_revision,
            "changed": changed,
        }
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core import (
    MAX_CONTENT_CHARS,
    MAX_READ_RESULTS,
    MAX_SEARCH_MATCHES,
    MAX_SEARCH_RESULTS,
    MAX_SEARCH_WHEN_TO_READ,
)

CanonicalName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description=(
            "Stable semantic name in lowercase kebab-case, for example "
            "retry-after-commit. This is not a filename."
        ),
    ),
]
ScopeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$",
        description=(
            "Semantic namespace id using lowercase letters/numbers with '.' or '-' "
            "separators. Never use '/' or a filesystem path."
        ),
    ),
]
KnowledgeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=260,
        description="Exact stable semantic knowledge id. This is not a filesystem path.",
    ),
]
Revision = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "Exact SHA-256 revision returned by knowledge_read. Supply only with id "
            "for updates."
        ),
    ),
]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Summary = Annotated[str, Field(min_length=1, max_length=500)]
WhenToRead = Annotated[str, Field(min_length=1, max_length=300)]
Keyword = Annotated[str, Field(min_length=1, max_length=120)]
SearchTerm = Annotated[str, Field(min_length=1, max_length=200)]
Locator = Annotated[str, Field(min_length=1, max_length=1000)]
SourceRef = Annotated[str, Field(min_length=1, max_length=200)]
SourceNote = Annotated[str, Field(min_length=1, max_length=1000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KnowledgeScope(StrictModel):
    kind: Literal["global", "system", "repo", "domain"] = Field(
        description=(
            "Semantic scope kind. It is a routing namespace, not an access-control "
            "boundary."
        )
    )
    id: ScopeId

    @model_validator(mode="before")
    @classmethod
    def explain_scope_id_separator_mistake(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        scope_id = value.get("id")
        if isinstance(scope_id, str) and "_" in scope_id:
            raise ValueError(
                "scope.id must use lowercase letters/numbers with '.' or '-' "
                f"separators, not '_': got {scope_id!r}. Use "
                f"{scope_id.replace('_', '-')!r} instead."
            )
        return value


class KnowledgeRouting(StrictModel):
    summary: Summary = Field(
        description=(
            "Retrieval abstract, not the full investigation. Hard maximum is 500 "
            "characters; before knowledge_write target 300 characters or less and "
            "measure deterministically when possible."
        )
    )

    @model_validator(mode="before")
    @classmethod
    def explain_summary_budget_overflow(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        summary = value.get("summary")
        if isinstance(summary, str) and len(summary) > 500:
            raise ValueError(
                f"routing.summary exceeds 500 characters ({len(summary)} given). "
                "routing.summary is a retrieval abstract, not overflow storage: move "
                "evidence, reasoning, and detailed uncertainty into content, then "
                "rewrite summary as 'durable conclusion + critical boundary' per the "
                "knowledge-distill Summary budget gate."
            )
        return value

    when_to_read: Annotated[
        list[WhenToRead],
        Field(
            min_length=1,
            max_length=20,
            description=(
                "Situations in which a future agent should retrieve this knowledge."
            ),
        ),
    ]
    keywords: Annotated[
        list[Keyword],
        Field(
            min_length=3,
            max_length=30,
            description=(
                "Canonical retrieval concepts. Prefer concise English technical terms."
            ),
        ),
    ]
    aliases: Annotated[
        list[Keyword],
        Field(
            max_length=30,
            description=(
                "Optional multilingual, legacy, acronym, or project-specific "
                "retrieval aliases."
            ),
        ),
    ] = Field(default_factory=list)


class KnowledgeSource(StrictModel):
    kind: Literal["repo", "document", "decision", "manual", "url"]
    locator: Locator = Field(
        description="Stable provenance locator that a human or agent can inspect."
    )
    ref: SourceRef | None = Field(
        default=None,
        description=(
            "Optional source revision, commit, version, or equivalent stable reference."
        ),
    )
    note: SourceNote | None = Field(
        default=None,
        description=(
            "Optional compact provenance pointer, not an evidence dump. Hard maximum "
            "is 1000 characters; before knowledge_write target 600 characters or less "
            "and measure deterministically when possible."
        ),
    )


class KnowledgeWriteEntry(StrictModel):
    id: KnowledgeId | None = Field(
        default=None,
        description="Update only: exact id from knowledge_read. Omit for create.",
    )
    expected_revision: Revision | None = Field(
        default=None,
        description=(
            "Update only: exact revision returned by knowledge_read. Omit for create."
        ),
    )
    canonical_name: CanonicalName
    title: Title
    scope: KnowledgeScope
    routing: KnowledgeRouting = Field(
        description=(
            "Retrieval metadata. summary, when_to_read, keywords, and aliases belong "
            "inside this object, never at the entry top level."
        )
    )
    content: Annotated[
        str,
        Field(
            max_length=MAX_CONTENT_CHARS,
            description=(
                "Free-form durable content. Vietnamese, English, or mixed language is "
                "allowed; do not add a language field."
            ),
        ),
    ]
    sources: Annotated[
        list[KnowledgeSource],
        Field(
            min_length=1,
            max_length=30,
            description="Evidence/provenance supporting the durable knowledge.",
        ),
    ]

    @model_validator(mode="before")
    @classmethod
    def explain_common_shape_mistakes(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        routing_fields = {"summary", "when_to_read", "keywords", "aliases"}
        misplaced = sorted(routing_fields.intersection(value))
        if misplaced:
            raise ValueError(
                "routing fields must be nested under the 'routing' object, not placed "
                f"at the entry top level: {', '.join(misplaced)}"
            )
        filesystem_fields = {"path", "filename", "directory", "index_path", "index"}
        filesystem = sorted(filesystem_fields.intersection(value))
        if filesystem:
            raise ValueError(
                "filesystem fields are owned by Knowledge MCP and must be omitted: "
                + ", ".join(filesystem)
            )
        if "language" in value:
            raise ValueError(
                "language is not part of the knowledge schema; content may be "
                "Vietnamese, English, or mixed"
            )
        return value

    @model_validator(mode="after")
    def validate_create_or_update(self) -> "KnowledgeWriteEntry":
        if self.id is None and self.expected_revision is not None:
            raise ValueError("create entries omit both id and expected_revision")
        if self.id is not None and self.expected_revision is None:
            raise ValueError(
                "update entries require expected_revision from knowledge_read together "
                "with id"
            )
        if self.id is not None:
            derived = f"{self.scope.kind}:{self.scope.id}:{self.canonical_name}"
            if self.id != derived:
                raise ValueError(
                    f"update id must match scope + canonical_name; expected {derived}"
                )
        return self


class KnowledgeSearchContext(StrictModel):
    repo: Annotated[str, Field(min_length=1, max_length=120)] | None = Field(
        default=None,
        description="Optional current-repository ranking hint only.",
    )
    domain: Annotated[str, Field(min_length=1, max_length=120)] | None = Field(
        default=None,
        description="Optional semantic-domain ranking hint only.",
    )


SearchKeywords = Annotated[
    list[SearchTerm],
    Field(
        min_length=1,
        max_length=20,
        description=(
            "Task-relevant search terms. Prefer several discriminative canonical "
            "concepts plus original-language/project aliases when useful."
        ),
    ),
]
SearchLimit = Annotated[
    int,
    Field(
        ge=1,
        le=MAX_SEARCH_RESULTS,
        description=(
            f"Maximum number of ranked decision cards to return (1-{MAX_SEARCH_RESULTS})."
        ),
    ),
]
ReadIds = Annotated[
    list[KnowledgeId],
    Field(
        min_length=1,
        max_length=MAX_READ_RESULTS,
        description=(
            f"Exact ids selected from knowledge_search to hydrate (1-{MAX_READ_RESULTS})."
        ),
    ),
]
WriteEntries = Annotated[
    list[KnowledgeWriteEntry],
    Field(
        max_length=20,
        description=(
            "Distilled entries to create/update. Pass [] after a completed knowledge "
            "review when nothing durable should be stored."
        ),
    ),
]


class KnowledgeChange(StrictModel):
    operation: Literal["created", "updated"]
    id: KnowledgeId
    path: str = Field(
        description="Canonical path chosen by Knowledge MCP. Informational output only."
    )
    revision: Revision


class KnowledgeWriteResult(StrictModel):
    reviewed: bool
    changes: list[KnowledgeChange]


class KnowledgeSearchMatch(StrictModel):
    query: SearchTerm
    field: Literal[
        "exact_id",
        "canonical_name",
        "keyword",
        "alias",
        "when_to_read",
        "summary",
    ]


class KnowledgeSearchHit(StrictModel):
    id: KnowledgeId
    title: Title
    scope: KnowledgeScope
    summary: Summary
    when_to_read: Annotated[
        list[WhenToRead],
        Field(min_length=1, max_length=MAX_SEARCH_WHEN_TO_READ),
    ]
    matches: Annotated[
        list[KnowledgeSearchMatch],
        Field(min_length=1, max_length=MAX_SEARCH_MATCHES),
    ]
    score: int


class KnowledgeSearchResult(StrictModel):
    results: list[KnowledgeSearchHit]


class KnowledgeReadItem(StrictModel):
    id: KnowledgeId
    revision: Revision
    canonical_name: CanonicalName
    title: Title
    scope: KnowledgeScope
    routing: KnowledgeRouting
    sources: list[KnowledgeSource]
    content: str


class KnowledgeReadResult(StrictModel):
    results: list[KnowledgeReadItem]

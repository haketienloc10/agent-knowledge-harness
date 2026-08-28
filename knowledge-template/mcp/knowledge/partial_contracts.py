from __future__ import annotations

from typing import Annotated, Any

from pydantic import ConfigDict, Field, model_validator

from contracts import (
    CanonicalName,
    Keyword,
    KnowledgeId,
    KnowledgeRouting,
    KnowledgeScope,
    KnowledgeSource,
    StrictModel,
    Summary,
    Title,
    WhenToRead,
)
from core import MAX_CONTENT_CHARS
from sections import MAX_SECTION_ID_CHARS


ExactReadRevision = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "Exact whole-document SHA-256 revision returned by an exact read surface: "
            "knowledge_read, knowledge_read_metadata, or knowledge_read_section. Use "
            "that exact revision as knowledge_update.expected_revision."
        ),
    ),
]
SectionId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_SECTION_ID_CHARS,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description=(
            "Stable semantic section id from an exact "
            "<!-- knowledge-section:... --> marker."
        ),
    ),
]
SectionHeading = Annotated[
    str,
    Field(
        min_length=4,
        max_length=300,
        description="Exact stored Markdown H2-H6 heading immediately after the section marker.",
    ),
]


class KnowledgeSectionSummary(StrictModel):
    id: SectionId
    heading: SectionHeading


class KnowledgeMetadataReadItem(StrictModel):
    id: KnowledgeId
    revision: ExactReadRevision
    canonical_name: CanonicalName
    title: Title
    scope: KnowledgeScope
    routing: KnowledgeRouting
    sources: list[KnowledgeSource]
    sections: list[KnowledgeSectionSummary]


class KnowledgeMetadataReadResult(StrictModel):
    results: list[KnowledgeMetadataReadItem]


class KnowledgeSectionReadResult(StrictModel):
    # Section body is semantic Markdown. Never apply model-wide string trimming to it:
    # indentation and trailing spaces can carry Markdown meaning.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id: KnowledgeId
    revision: ExactReadRevision
    section_id: SectionId
    heading: SectionHeading
    content: Annotated[str, Field(max_length=MAX_CONTENT_CHARS)]


def _reject_explicit_null(model: StrictModel) -> StrictModel:
    for field_name in model.model_fields_set:
        if getattr(model, field_name) is None:
            raise ValueError(f"{field_name} cannot be null; omit it when unchanged")
    return model


class KnowledgeRoutingPatch(StrictModel):
    summary: Summary | None = None
    when_to_read: Annotated[list[WhenToRead], Field(min_length=1, max_length=20)] | None = None
    keywords: Annotated[list[Keyword], Field(min_length=3, max_length=30)] | None = None
    aliases: Annotated[list[Keyword], Field(max_length=30)] | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "KnowledgeRoutingPatch":
        _reject_explicit_null(self)
        if not self.model_fields_set:
            raise ValueError("routing patch must contain at least one changed field")
        return self


class KnowledgeMetadataPatch(StrictModel):
    title: Title | None = None
    routing: KnowledgeRoutingPatch | None = None
    sources: Annotated[list[KnowledgeSource], Field(min_length=1, max_length=30)] | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "KnowledgeMetadataPatch":
        _reject_explicit_null(self)
        if not self.model_fields_set:
            raise ValueError("metadata patch must contain at least one changed field")
        return self


class KnowledgeSectionPatch(StrictModel):
    # Preserve the replacement body byte-for-byte at the semantic string level. The
    # section id itself is canonical and therefore does not need whitespace coercion.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    id: SectionId
    content: Annotated[
        str,
        Field(
            max_length=MAX_CONTENT_CHARS,
            description=(
                "Replacement body for this existing section only. Do not include the "
                "live knowledge-section marker or the stored section heading. Fenced "
                "Markdown examples of marker syntax are allowed."
            ),
        ),
    ]


class KnowledgePatch(StrictModel):
    metadata: KnowledgeMetadataPatch | None = None
    content: Annotated[
        str,
        Field(
            max_length=MAX_CONTENT_CHARS,
            description=(
                "Optional replacement for the entire semantic content body. Existing "
                "metadata remains unchanged unless metadata is also supplied."
            ),
        ),
    ] | None = None
    section: KnowledgeSectionPatch | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "KnowledgePatch":
        _reject_explicit_null(self)
        if not self.model_fields_set:
            raise ValueError("knowledge patch must contain at least one mutation")
        if "content" in self.model_fields_set and "section" in self.model_fields_set:
            raise ValueError("full content replacement and section replacement are mutually exclusive")
        return self

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True, mode="python")

from __future__ import annotations

import datetime

from pydantic import BaseModel, model_validator


class NovelCreate(BaseModel):
    name: str
    title: str | None = None
    source_language: str = "korean"


class ChapterSummary(BaseModel):
    id: int
    chapter_number: int
    source_type: str
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class NovelResponse(BaseModel):
    id: int
    name: str
    title: str | None
    source_language: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    chapter_count: int = 0

    model_config = {"from_attributes": True}


class NovelDetail(NovelResponse):
    chapters: list[ChapterSummary] = []
    policy_count: int = 0
    glossary_count: int = 0


class ChapterCreate(BaseModel):
    chapter_number: int
    source_type: str  # 'mtl' or 'original'
    raw_text: str

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def validate_fields(self) -> "ChapterCreate":
        if self.source_type not in ("mtl", "original"):
            raise ValueError(f"source_type must be 'mtl' or 'original', got '{self.source_type}'")
        if not self.raw_text.strip():
            raise ValueError("raw_text must not be empty")
        if self.chapter_number < 1:
            raise ValueError("chapter_number must be >= 1")
        return self


class ChapterResponse(BaseModel):
    id: int
    novel_id: int
    chapter_number: int
    source_type: str
    raw_text: str
    refined_text: str | None
    status: str
    error_message: str | None
    warnings: str | None
    processing_time_ms: int | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class ChapterRead(BaseModel):
    id: int
    chapter_number: int
    raw_text: str
    refined_text: str | None
    status: str
    source_type: str

    model_config = {"from_attributes": True}


class ChapterStatusResponse(BaseModel):
    """Lightweight response for polling chapter status without transferring megabytes of text."""

    id: int
    novel_id: int
    chapter_number: int
    source_type: str
    status: str
    error_message: str | None
    warnings: str | None
    processing_time_ms: int | None

    model_config = {"from_attributes": True}


class ProcessRequest(BaseModel):
    do_llm: bool = True


class PolicyResponse(BaseModel):
    id: int
    novel_id: int
    policy_id: str
    type: str
    trigger: str
    match_forms: str
    action: str
    confidence: float
    evidence_chapters: str | None
    applies: str
    note: str | None
    needs_review: str | None = None
    metadata_json: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class GlossaryResponse(BaseModel):
    id: int
    novel_id: int
    canonical: str
    aliases: str
    entity_type: str | None
    confidence: float | None
    evidence_contexts: str | None = None
    metadata_json: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class GlossaryMetadataUpdate(BaseModel):
    metadata_json: str
    needs_review: bool = False
    apply_proposed: bool = False


class MergeGlossaryRequest(BaseModel):
    target_id: int
    source_ids: list[int]
    deterministic_ids: list[int] | None = None


class DuplicateClusterResponse(BaseModel):
    cluster_id: str
    target: GlossaryResponse
    candidates: list[GlossaryResponse]
    reason: str


class ExtractLoreRequest(BaseModel):
    chapter_ids: list[int] | None = None
    only_og_tl: bool = False
    bypass_review: bool = False


class JobResponse(BaseModel):
    id: int
    chapter_id: int
    chapter_number: int | None = None
    job_type: str
    status: str
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    error_message: str | None
    result_summary: str | None

    model_config = {"from_attributes": True}


class JobStatus(BaseModel):
    job_id: int
    status: str
    chapter_id: int
    chapter_number: int | None = None
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None


class PolicyCreate(BaseModel):
    trigger: str
    replacement: str
    note: str | None = None


class PolicyUpdate(BaseModel):
    trigger: str | None = None
    replacement: str | None = None
    note: str | None = None


class StyleSnippetCreate(BaseModel):
    text: str
    note: str | None = None


class StyleSnippetUpdate(BaseModel):
    text: str | None = None
    note: str | None = None


class StyleSnippetResponse(BaseModel):
    id: int
    novel_id: int
    text: str
    note: str | None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}

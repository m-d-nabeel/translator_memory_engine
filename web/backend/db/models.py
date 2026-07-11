from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Novel(Base):
    __tablename__ = "novels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    source_language = Column(String, nullable=False, default="korean")
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    chapters = relationship(
        "Chapter", back_populates="novel", cascade="all, delete-orphan"
    )
    policies = relationship(
        "Policy", back_populates="novel", cascade="all, delete-orphan"
    )
    glossary_entries = relationship(
        "GlossaryEntry", back_populates="novel", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("novel_id", "chapter_number", "source_type"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    source_type = Column(String, nullable=False)  # 'mtl' or 'original'
    raw_text = Column(Text, nullable=False)
    refined_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    novel = relationship("Novel", back_populates="chapters")
    jobs = relationship("ProcessingJob", back_populates="chapter", cascade="all, delete-orphan")


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("novel_id", "policy_id", name="uq_novel_policy"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    policy_id = Column(String, nullable=False)
    type = Column(String, nullable=False)
    trigger = Column(String, nullable=False)
    match_forms = Column(Text, nullable=False)  # JSON array
    action = Column(Text, nullable=False)  # JSON object
    confidence = Column(Float, nullable=False)
    evidence_chapters = Column(Text, nullable=True)  # JSON array
    applies = Column(String, nullable=False, default="deterministic")
    scores = Column(Text, nullable=True)  # JSON object: {frequency, consistency, context}
    category = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    needs_review = Column(String, nullable=False, default="false")  # stored as "true"/"false" for SQLite compat
    llm_rejected = Column(String, nullable=False, default="false")  # stored as "true"/"false" for SQLite compat
    contexts = Column(Text, nullable=True)  # JSON array: example sentences
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    novel = relationship("Novel", back_populates="policies")


class GlossaryEntry(Base):
    __tablename__ = "glossary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    canonical = Column(String, nullable=False)
    aliases = Column(Text, nullable=False)  # JSON array
    entity_type = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)

    novel = relationship("Novel", back_populates="glossary_entries")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String, nullable=False)  # extract/rewrite/eval
    status = Column(String, nullable=False, default="queued")  # queued/running/completed/failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)  # JSON summary

    chapter = relationship("Chapter", back_populates="jobs")

    @property
    def chapter_number(self) -> int | None:
        return self.chapter.chapter_number if self.chapter else None

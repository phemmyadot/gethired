"""
SQLAlchemy models for JobBot.
All tables with dedup guards and full audit trail.
"""
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, String, Float, Text, DateTime,
    Boolean, ForeignKey, ARRAY, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, Session
from sqlalchemy.sql import func
import uuid
import os

backend_dir = Path(__file__).resolve().parents[2]
for env_file in (backend_dir / ".env.local", backend_dir / ".env"):
    load_dotenv(env_file, override=False)

Base = declarative_base()

def get_engine():
    return create_engine(os.getenv("DATABASE_URL", "postgresql://jobbot:jobbot@localhost/jobbot"))

def get_session():
    engine = get_engine()
    return Session(engine)


class Resume(Base):
    __tablename__ = "resumes"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), nullable=False)
    filename    = Column(String(255), nullable=False)
    label       = Column(String(100))           # e.g. "Backend Engineer", "Data Analyst"
    content     = Column(Text, nullable=False)  # extracted plain text
    file_path   = Column(String(500))           # path to original file
    active      = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    matches     = relationship("JobMatch", back_populates="resume")
    applications = relationship("AppliedJob", back_populates="resume")


class Job(Base):
    __tablename__ = "jobs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source      = Column(String(50), nullable=False)      # "adzuna", "remotive", "greenhouse"
    external_id = Column(String(255), nullable=False)     # source's job ID
    title       = Column(String(255), nullable=False)
    company     = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    location    = Column(String(255))
    remote      = Column(Boolean, default=False)
    salary_min  = Column(Float)
    salary_max  = Column(Float)
    apply_url   = Column(String(1000), nullable=False)
    expired     = Column(Boolean, default=False)
    fetched_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_job_source_external"),
        Index("ix_jobs_fetched", "fetched_at"),
        Index("ix_jobs_source", "source"),
    )

    matches      = relationship("JobMatch", back_populates="job")
    applications = relationship("AppliedJob", back_populates="job")


class JobMatch(Base):
    __tablename__ = "job_matches"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id         = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    resume_id      = Column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=False)
    score          = Column(Float, nullable=False)          # 0.0 – 1.0
    reasoning      = Column(Text)
    missing_skills = Column(ARRAY(Text), default=[])
    selling_points = Column(ARRAY(Text), default=[])
    reviewed_at    = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("job_id", "resume_id", name="uq_match_job_resume"),
        Index("ix_matches_score", "score"),
    )

    job    = relationship("Job", back_populates="matches")
    resume = relationship("Resume", back_populates="matches")


class AppliedJob(Base):
    __tablename__ = "applied_jobs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id       = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, unique=True)
    resume_id    = Column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=False)
    match_score  = Column(Float)
    cover_letter = Column(Text)
    status       = Column(String(50), default="applied")  # applied|failed|skipped|interview|rejected|offer
    applied_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, onupdate=datetime.utcnow)
    error_msg    = Column(Text)
    notes        = Column(Text)                            # manual recruiter notes

    job    = relationship("Job", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source      = Column(String(50))
    jobs_found  = Column(Float, default=0)
    jobs_new    = Column(Float, default=0)
    jobs_duped  = Column(Float, default=0)
    error       = Column(Text)
    ran_at      = Column(DateTime, default=datetime.utcnow)
    duration_s  = Column(Float)

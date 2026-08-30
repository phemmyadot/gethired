"""
Ingestion pipeline: fetch → pre-filter → dedup → save.
Returns list of newly inserted Job records for matching.
"""
import logging
import os
import time
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .sources import (
    fetch_adzuna, fetch_remotive,
    fetch_greenhouse_all, fetch_lever_all,
)
from ..db.models import Job, IngestionLog

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Pre-filter: cheap checks before Claude
# ─────────────────────────────────────────────

DEFAULT_BLOCKED_TITLES = [
    "principal", "vp ", "vice president", "c-level", "cto", "ceo",
    "unpaid", "internship", "volunteer",
]

DEFAULT_REQUIRED_KEYWORDS: list[str] = []  # e.g. ["python", "react"]

def _default_sources() -> list[str]:
    sources = ["adzuna", "remotive"]
    if os.getenv("GREENHOUSE_ENABLED", "false").lower() == "true":
        sources.append("greenhouse")
    if os.getenv("LEVER_ENABLED", "false").lower() == "true":
        sources.append("lever")
    return sources

def pre_filter(job: dict, prefs: dict = None) -> bool:
    """
    Returns True if job passes basic filters and should be sent to Claude.
    Saves API cost by ruling out obvious mismatches early.
    """
    prefs = prefs or {}
    title_lower = job["title"].lower()
    desc_lower  = job["description"].lower()

    # Block certain title patterns
    blocked_titles = prefs.get("blocked_titles", DEFAULT_BLOCKED_TITLES)
    if any(b in title_lower for b in blocked_titles):
        return False

    # Require at least one keyword if configured
    required = prefs.get("required_keywords", DEFAULT_REQUIRED_KEYWORDS)
    if required and not any(k.lower() in desc_lower for k in required):
        return False

    # Salary floor
    min_salary = prefs.get("min_salary")
    if min_salary and job.get("salary_max") and job["salary_max"] < min_salary:
        return False

    # Must have description
    if len(job["description"]) < 100:
        return False

    # Must have apply URL
    if not job["apply_url"]:
        return False

    return True


# ─────────────────────────────────────────────
# Save to DB (with dedup via UNIQUE constraint)
# ─────────────────────────────────────────────

def save_job(job_dict: dict, db: Session) -> tuple[Job | None, bool]:
    """
    Insert job if new. Returns (Job, is_new).
    Duplicate (source, external_id) → returns (existing, False).
    """
    existing = db.query(Job).filter_by(
        source=job_dict["source"],
        external_id=job_dict["external_id"]
    ).first()

    if existing:
        return existing, False

    job = Job(**job_dict)
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, True
    except IntegrityError:
        db.rollback()
        existing = db.query(Job).filter_by(
            source=job_dict["source"],
            external_id=job_dict["external_id"]
        ).first()
        return existing, False


# ─────────────────────────────────────────────
# Main ingestion entry point
# ─────────────────────────────────────────────

def run_ingestion(db: Session, prefs: dict = None, sources: list[str] = None) -> list[Job]:
    """
    Fetch from all sources, pre-filter, dedup, save.
    Returns list of newly inserted Job objects ready for matching.
    """
    sources = sources or _default_sources()
    all_raw: list[dict] = []

    # 1. Fetch
    if "adzuna" in sources:
        keywords = (prefs or {}).get("keywords", "software engineer")
        all_raw.extend(fetch_adzuna(keywords=keywords))

    if "remotive" in sources:
        search = (prefs or {}).get("keywords", "")
        all_raw.extend(fetch_remotive(search=search))

    if "greenhouse" in sources:
        all_raw.extend(fetch_greenhouse_all())

    if "lever" in sources:
        all_raw.extend(fetch_lever_all())

    logger.info(f"Ingestion: {len(all_raw)} total raw jobs from {len(sources)} sources")

    # 2. Pre-filter
    filtered = [j for j in all_raw if pre_filter(j, prefs)]
    logger.info(f"Pre-filter: {len(filtered)}/{len(all_raw)} passed")

    # 3. Save (dedup via DB unique constraint)
    new_jobs: list[Job] = []
    duped = 0
    start = time.time()

    for job_dict in filtered:
        job, is_new = save_job(job_dict, db)
        if is_new:
            new_jobs.append(job)
        else:
            duped += 1

    duration = round(time.time() - start, 2)
    logger.info(f"Saved {len(new_jobs)} new jobs, {duped} duplicates skipped in {duration}s")

    # 4. Log run
    log = IngestionLog(
        source=",".join(sources),
        jobs_found=len(all_raw),
        jobs_new=len(new_jobs),
        jobs_duped=duped,
        duration_s=duration,
    )
    db.add(log)
    db.commit()

    return new_jobs

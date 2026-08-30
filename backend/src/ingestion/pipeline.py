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
    fetch_adzuna, fetch_remotive, fetch_remoteok, fetch_jobicy, fetch_arbeitnow,
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
    sources = ["adzuna", "remotive", "remoteok", "jobicy", "arbeitnow"]
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

def _parse_posted_at(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


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

    job_dict = {**job_dict, "posted_at": _parse_posted_at(job_dict.get("posted_at"))}
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

SENIORITY_PREFIXES = ["senior", "sr", "sr.", "lead", "staff", "principal"]

def _keyword_variants(keywords: str) -> list[str]:
    """
    If keywords lead with a seniority word (e.g. "senior software engineer"),
    also search the title without it ("software engineer") — many postings for
    the same level of role omit the seniority prefix entirely.
    """
    keywords = keywords.strip()
    if not keywords:
        return [keywords]

    words = keywords.split()
    if words[0].lower() not in SENIORITY_PREFIXES:
        return [keywords]

    stripped = " ".join(words[1:]).strip()
    return [keywords, stripped] if stripped else [keywords]


def run_ingestion(db: Session, prefs: dict = None, sources: list[str] = None, log: IngestionLog = None) -> list[Job]:
    """
    Fetch from all sources, pre-filter, dedup, save.
    Returns list of newly inserted Job objects ready for matching.
    If `log` is given, updates that row's counts instead of creating a new one.
    """
    sources = sources or _default_sources()
    all_raw: list[dict] = []
    keyword_variants = _keyword_variants((prefs or {}).get("keywords", "software engineer"))

    # 1. Fetch — search each keyword variant (e.g. with and without "senior")
    for keywords in keyword_variants:
        if "adzuna" in sources:
            all_raw.extend(fetch_adzuna(keywords=keywords))

        if "remotive" in sources:
            all_raw.extend(fetch_remotive(search=keywords))

        if "remoteok" in sources:
            all_raw.extend(fetch_remoteok(search=keywords))

        if "jobicy" in sources:
            all_raw.extend(fetch_jobicy(search=keywords))

        if "arbeitnow" in sources:
            all_raw.extend(fetch_arbeitnow(search=keywords))

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
    if log is None:
        log = IngestionLog(source=",".join(sources))
        db.add(log)
    else:
        log.source = ",".join(sources)
    log.jobs_found = len(all_raw)
    log.jobs_new = len(new_jobs)
    log.jobs_duped = duped
    log.duration_s = duration
    db.commit()

    return new_jobs

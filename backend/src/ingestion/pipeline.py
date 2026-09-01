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
    fetch_greenhouse_all, fetch_lever_all, fetch_ashby_all,
    GREENHOUSE_COMPANIES, LEVER_COMPANIES,
    slug_candidates, PROBE_FUNCS,
)
from ..db.models import Job, IngestionLog, DiscoveredAtsCompany

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Pre-filter: cheap checks before Claude
# ─────────────────────────────────────────────

DEFAULT_BLOCKED_TITLES = [
    "principal", "vp ", "vice president", "c-level", "cto", "ceo",
    "unpaid", "internship", "volunteer",
]

DEFAULT_REQUIRED_KEYWORDS: list[str] = []  # e.g. ["python", "react"]

# Non-US signals in free-text location fields. Blacklist approach (not
# whitelist) because US locations are wildly varied (city/state/county
# combos, "Remote", "Hybrid", "N/A", etc.) but non-US country/city names are
# a much smaller, more reliable set to match against.
NON_US_LOCATION_SIGNALS = [
    "india", "bengaluru", "bangalore", "gurugram", "gurgaon", "pune", "delhi",
    "hyderabad", "mumbai", "chennai", "noida",
    "singapore", "hong kong", "japan", "tokyo", "south korea", "seoul",
    "china", "shanghai", "beijing", "taiwan", "taipei", "vietnam", "hanoi",
    "philippines", "manila", "indonesia", "jakarta", "malaysia", "kuala lumpur",
    "thailand", "bangkok",
    "united kingdom", "england", " uk", "uk ", "uk,", "uk)", "uk-", "-uk",
    "london", "dublin", "ireland", "germany", "berlin", "munich", "hamburg",
    "cologne", "france", "paris", "netherlands", "amsterdam", "spain", "madrid",
    "barcelona", "italy", "milan", "rome", "portugal", "lisbon", "poland",
    "warsaw", "finland", "helsinki", "sweden", "stockholm", "norway", "oslo",
    "denmark", "copenhagen", "switzerland", "zurich", "austria", "vienna",
    "belgium", "brussels", "serbia", "belgrade", "greece", "athens", "romania",
    "bucharest", "deutschland", "europe",
    "canada", "toronto", "montreal", "vancouver", "ottawa",
    "mexico", "mexico city", "colombia", "bogota", "brazil", "sao paulo",
    "argentina", "buenos aires", "chile", "santiago", "peru",
    "australia", "sydney", "melbourne", "new zealand", "auckland",
    "south africa", "nigeria", "kenya", "egypt", "israel", "tel aviv",
    "united arab emirates", "dubai", "saudi arabia",
]

US_OVERRIDE_SIGNALS = ["united states", "usa", "u.s.", " us ", " us,", " us)", "us-", "-us"]


def _is_non_us_location(location: str) -> bool:
    """
    Best-effort US-only filter on free-text location strings from various
    sources. Only blocks when a non-US signal is present AND no explicit
    US signal is also present (many ATS postings list multiple offices,
    e.g. "San Francisco, CA | London, UK" — we don't want to drop those
    since a US office is available).
    """
    if not location:
        return False
    loc = f" {location.lower()} "
    has_non_us = any(sig in loc for sig in NON_US_LOCATION_SIGNALS)
    if not has_non_us:
        return False
    has_us = any(sig in loc for sig in US_OVERRIDE_SIGNALS)
    return not has_us

def _default_sources() -> list[str]:
    sources = ["adzuna", "remotive", "remoteok", "jobicy", "arbeitnow"]
    if os.getenv("GREENHOUSE_ENABLED", "false").lower() == "true":
        sources.append("greenhouse")
    if os.getenv("LEVER_ENABLED", "false").lower() == "true":
        sources.append("lever")
    if os.getenv("ASHBY_ENABLED", "true").lower() == "true":
        sources.append("ashby")
    return sources


AGGREGATOR_SOURCES = {"adzuna", "remotive", "remoteok", "jobicy", "arbeitnow"}
ATS_SOURCES = ["greenhouse", "lever", "ashby"]
DISCOVERY_PROBE_CAP = int(os.getenv("ATS_DISCOVERY_PROBE_CAP", "10"))  # new companies probed per source per run


def discover_ats_companies(db: Session, company_names: set[str]) -> None:
    """
    For each company name seen in this run's aggregator results, check
    whether it also has a Greenhouse/Lever/Ashby board — cache the result
    (confirmed or not_found) so it's never re-probed. Capped per source per
    run to keep ingestion latency bounded; makes steady progress over time
    rather than trying to resolve everything at once.
    """
    for source in ATS_SOURCES:
        already_checked = {
            r[0] for r in db.query(DiscoveredAtsCompany.company_name)
            .filter_by(source=source).all()
        }
        candidates = [c for c in company_names if c and c not in already_checked][:DISCOVERY_PROBE_CAP]
        if not candidates:
            continue

        probe = PROBE_FUNCS[source]
        for company_name in candidates:
            confirmed_token = None
            for slug in slug_candidates(company_name):
                try:
                    if probe(slug):
                        confirmed_token = slug
                        break
                except Exception as e:
                    logger.debug(f"Probe error for {source}/{slug}: {e}")

            db.add(DiscoveredAtsCompany(
                company_name=company_name,
                source=source,
                board_token=confirmed_token,
                status="confirmed" if confirmed_token else "not_found",
            ))
        db.commit()
        logger.info(
            f"ATS discovery [{source}]: probed {len(candidates)} companies, "
            f"{sum(1 for c in candidates if c)} attempted"
        )


def _confirmed_tokens(db: Session, source: str) -> list[str]:
    rows = db.query(DiscoveredAtsCompany.board_token).filter_by(source=source, status="confirmed").all()
    return [r[0] for r in rows if r[0]]

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

    # US-only: drop jobs whose location is clearly outside the US
    if _is_non_us_location(job.get("location", "")):
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

    # Discover new Greenhouse/Lever/Ashby companies from aggregator-sourced
    # company names before fetching those ATS sources, so newly-confirmed
    # tokens are included in this same run's fetch.
    aggregator_companies = {j["company"] for j in all_raw if j.get("source") in AGGREGATOR_SOURCES}
    if aggregator_companies:
        discover_ats_companies(db, aggregator_companies)

    if "greenhouse" in sources:
        companies = list(set(GREENHOUSE_COMPANIES) | set(_confirmed_tokens(db, "greenhouse")))
        all_raw.extend(fetch_greenhouse_all(companies=companies))

    if "lever" in sources:
        companies = list(set(LEVER_COMPANIES) | set(_confirmed_tokens(db, "lever")))
        all_raw.extend(fetch_lever_all(companies=companies))

    if "ashby" in sources:
        all_raw.extend(fetch_ashby_all(companies=_confirmed_tokens(db, "ashby") or None))

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

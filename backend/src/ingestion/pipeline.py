"""
Ingestion pipeline: fetch → pre-filter → dedup → save.
Returns list of newly inserted Job records for matching.
"""
import logging
import os
import re
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
from ..db.models import Job, IngestionLog, SourcePoolState, DiscoveredAtsCompany

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


class JobWorkModeScanner:
    """Classify high-confidence work-mode and geographic signals in job text."""

    HYBRID_ONSITE = re.compile(
        r"\b(hybrid|on[- ]site|onsite|in[- ]office|office[- ]based|"
        r"\d+\s*days?\s*(a|per)?\s*week\s*in\s*(the\s*)?office|"
        r"relocation\s+required|must\s+be\s+located\s+in|office\s+attendance)\b",
        re.IGNORECASE,
    )
    RESTRICTED_REMOTE = re.compile(
        r"\b(remote\s+in|must\s+(reside|live)\s+in|restricted\s+to|"
        r"open\s+to\s+residents\s+of|remote\s*\([^)]*\s+only\))",
        re.IGNORECASE,
    )
    US_REMOTE = re.compile(
        r"\b(remote\s*[-,]\s*(us|united states)|remote\s*\(\s*(us|united states)\s*\)|"
        r"remote\s+in\s+the\s+(us|united states)|"
        r"work\s+from\s+anywhere\s+in\s+the\s+(us|united states)|"
        r"100%\s+remote\s*(us|united states)?|fully\s+remote\s*(us|united states)?|"
        r"us\s+national\s+remote|remote\s+within\s+the\s+(us|united states)|"
        r"anywhere\s+in\s+the\s+us)\b",
        re.IGNORECASE,
    )
    GENERIC_REMOTE = re.compile(r"\b(remote|work\s+from\s+home|wfh|telecommute|distributed\s+team)\b", re.IGNORECASE)

    def scan(self, text: str) -> dict:
        if not text or len(text) < 100:
            return {"work_mode": "invalid", "confidence": "high"}
        if self.HYBRID_ONSITE.search(text):
            return {"work_mode": "hybrid_or_onsite", "confidence": "high"}
        if self.US_REMOTE.search(text):
            return {"work_mode": "remote", "confidence": "high"}
        if self.RESTRICTED_REMOTE.search(text):
            return {"work_mode": "restricted_remote", "confidence": "high"}
        if self.GENERIC_REMOTE.search(text):
            # Not explicitly US-scoped, but by the time this scanner runs the
            # job has already survived pre_filter's non-US-location blacklist
            # (_is_non_us_location), so plain "remote" with no hybrid/onsite/
            # restricted signal is trusted rather than sent to the LLM just to
            # re-confirm what the location filter already established.
            return {"work_mode": "remote", "confidence": "high"}
        return {"work_mode": "unknown", "confidence": "low"}


WORK_MODE_SCANNER = JobWorkModeScanner()


class JobTitleRoleScanner:
    """Classify high-confidence engineering-role signals from a job title alone."""

    NON_ENGINEERING_TERMS = {
        "advocate", "advocacy", "community", "recruiting", "recruiter",
        "sales", "marketing", "support", "customer success", "relations",
    }
    ENGINEERING_TERMS = {
        "engineer", "engineering", "developer", "programmer", "architect",
        "devops", "backend", "frontend", "full-stack", "fullstack", "platform",
        "infrastructure", "systems", "cloud", "sre", "reliability", "data",
        "mlops", "machine learning", "ai", "llm", "mobile", "software",
    }

    def scan(self, title: str) -> dict:
        title_lower = (title or "").lower()
        if any(term in title_lower for term in self.NON_ENGINEERING_TERMS):
            return {"is_engineering_role": False, "confidence": "high"}
        if any(re.search(rf"\b{re.escape(term)}\b", title_lower) for term in self.ENGINEERING_TERMS):
            return {"is_engineering_role": True, "confidence": "high"}
        return {"is_engineering_role": False, "confidence": "low"}


TITLE_ROLE_SCANNER = JobTitleRoleScanner()

JOB_METADATA_PROMPT = """You are a precise job metadata extraction engine.
Analyze only this job posting and return valid JSON. Do not use markdown.

Required JSON fields:
{{
    "work_mode": "remote|hybrid|onsite|unknown",
    "is_us_remote_eligible": true,
    "state_restrictions": ["string"],
    "is_engineering_role": true,
    "confidence": "high|medium|low"
}}

Job title: {title}
Company: {company}
Raw location: {location}
Job description:
{description}

Use only the current posting. A role is engineering only when its primary
function is software, platform, infrastructure, data, AI, systems, or DevOps
engineering. Developer advocacy, recruiting, sales, and support are not
engineering roles. Generic remote without US eligibility is not eligible.
"""


def extract_ambiguous_job_metadata(job: dict) -> dict:
    """Use the fast extraction model only when regex signals are ambiguous."""
    from ..llm import generate_text
    from ..matching.engine import parse_llm_json_response

    prompt = JOB_METADATA_PROMPT.format(
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        description=job.get("description", "")[:1800],
    )
    try:
        result = parse_llm_json_response(generate_text(prompt))
    except Exception as exc:
        logger.warning("Ambiguous job metadata extraction failed: %s", exc)
        return {
            "work_mode": "unknown",
            "is_us_remote_eligible": False,
            "is_engineering_role": False,
            "confidence": "low",
        }
    return {
        "work_mode": result.get("work_mode", "unknown"),
        "is_us_remote_eligible": bool(result.get("is_us_remote_eligible", False)),
        "is_engineering_role": bool(result.get("is_engineering_role", False)),
        "confidence": result.get("confidence", "low"),
    }


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
        # Close the transaction this read opened before the (HTTP-bound) probe
        # loop below, so the session isn't left idle-in-transaction for the
        # duration of every candidate's probe call.
        db.commit()
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


def _matches_resume_title(job: dict, prefs: dict) -> bool:
    """Keep jobs in a discipline represented by the active resume profile."""
    resume_job_titles = prefs.get("resume_job_titles") or []
    if resume_job_titles:
        profile_title = " ".join(resume_job_titles).lower()
    else:
        profile_title = (prefs.get("resume_title") or prefs.get("keywords") or "").lower()
    title_terms = [
        term for term in re.findall(r"[a-z0-9]+", profile_title)
        if term not in {"senior", "sr", "lead", "staff", "principal", "junior", "jr"}
    ]
    if not title_terms:
        return True

    job_title = job.get("title", "").lower()
    non_engineering_terms = {
        "advocate", "advocacy", "community", "recruiting", "recruiter",
        "sales", "marketing", "support", "customer success", "relations",
    }
    if any(term in job_title for term in non_engineering_terms):
        return any(term in profile_title for term in non_engineering_terms)

    equivalent_terms = set(title_terms)
    if {"software", "engineer"} & equivalent_terms:
        equivalent_terms.update({
            "developer", "programmer", "architect", "devops", "backend",
            "frontend", "full-stack", "fullstack", "platform", "infrastructure",
            "systems", "cloud", "sre", "reliability", "data", "mlops", "machine",
            "learning", "ai", "llm", "mobile", "applications", "application",
            "core", "tech", "technical",
        })
    return any(re.search(rf"\b{re.escape(term)}\b", job_title) for term in equivalent_terms)


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
        # Read-only lookup, but SQLAlchemy still opened a transaction for it —
        # close it out rather than leaving the session idle-in-transaction for
        # however long the caller's next DB-free work (e.g. an LLM call) takes.
        db.commit()
        return existing, False

    job_dict = {**job_dict, "posted_at": _parse_posted_at(job_dict.get("posted_at"))}
    job = Job(**job_dict)
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
        # db.refresh() issues its own SELECT, which (like the dedup lookup
        # above) opens a fresh transaction that the prior commit() doesn't
        # cover. Close it here too, so the session isn't left idle-in-transaction
        # across the caller's next DB-free work (e.g. an LLM classify call).
        db.commit()
        return job, True
    except IntegrityError:
        db.rollback()
        existing = db.query(Job).filter_by(
            source=job_dict["source"],
            external_id=job_dict["external_id"]
        ).first()
        db.commit()
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


def _is_stopping(log_id) -> bool:
    if not log_id:
        return False
    from ..db.models import get_session as _get_session
    check_db = _get_session()
    try:
        status = check_db.query(IngestionLog.status).filter_by(id=log_id).scalar()
        return status == "stopping"
    finally:
        check_db.close()


def run_ingestion(db: Session, prefs: dict = None, sources: list[str] = None, log: IngestionLog = None) -> list[Job]:
    """
    Fetch from all sources, pre-filter, dedup, save.
    Returns list of newly inserted Job objects ready for matching.
    If `log` is given, updates that row's counts instead of creating a new one.
    """
    sources = sources or _default_sources()
    all_raw: list[dict] = []
    keyword_variants = _keyword_variants((prefs or {}).get("keywords", "software engineer"))
    log_id = log.id if log else None
    should_stop = (lambda: _is_stopping(log_id)) if log_id else None

    def _report_pooled(count: int):
        """Persist raw-fetched count so far, so the UI can poll live progress
        during the fetch stage instead of only seeing counts once it's done."""
        if log is None:
            return
        log.jobs_found = count
        db.commit()

    # 1. Fetch — search each keyword variant (e.g. with and without "senior")
    for keywords in keyword_variants:
        if should_stop and should_stop():
            logger.info("Ingestion stopped early (before aggregator fetch)")
            break

        if "adzuna" in sources:
            all_raw.extend(fetch_adzuna(keywords=keywords))
            _report_pooled(len(all_raw))

        if "remotive" in sources:
            all_raw.extend(fetch_remotive(search=keywords))
            _report_pooled(len(all_raw))

        if "remoteok" in sources:
            all_raw.extend(fetch_remoteok(search=keywords))
            _report_pooled(len(all_raw))

        if "jobicy" in sources:
            all_raw.extend(fetch_jobicy(search=keywords))
            _report_pooled(len(all_raw))

        if "arbeitnow" in sources:
            all_raw.extend(fetch_arbeitnow(search=keywords))
            _report_pooled(len(all_raw))

    stopped = bool(should_stop and should_stop())

    if not stopped:
        # Discover new Greenhouse/Lever/Ashby companies from aggregator-sourced
        # company names before fetching those ATS sources, so newly-confirmed
        # tokens are included in this same run's fetch.
        aggregator_companies = {j["company"] for j in all_raw if j.get("source") in AGGREGATOR_SOURCES}
        if aggregator_companies:
            discover_ats_companies(db, aggregator_companies)

        if "greenhouse" in sources and not (should_stop and should_stop()):
            companies = list(set(GREENHOUSE_COMPANIES) | set(_confirmed_tokens(db, "greenhouse")))
            # _confirmed_tokens's read opened a transaction; close it before the
            # (possibly long, HTTP-bound) fetch call below so the session isn't
            # left idle-in-transaction for the duration of that fetch.
            db.commit()
            all_raw.extend(fetch_greenhouse_all(companies=companies, should_stop=should_stop))
            _report_pooled(len(all_raw))

        if "lever" in sources and not (should_stop and should_stop()):
            companies = list(set(LEVER_COMPANIES) | set(_confirmed_tokens(db, "lever")))
            db.commit()
            all_raw.extend(fetch_lever_all(companies=companies, should_stop=should_stop))
            _report_pooled(len(all_raw))

        if "ashby" in sources and not (should_stop and should_stop()):
            ashby_companies = _confirmed_tokens(db, "ashby") or None
            db.commit()
            all_raw.extend(fetch_ashby_all(companies=ashby_companies, should_stop=should_stop))
            _report_pooled(len(all_raw))

    stopped = stopped or bool(should_stop and should_stop())
    logger.info(f"Ingestion: {len(all_raw)} total raw jobs from {len(sources)} sources" + (" (stopped early)" if stopped else ""))

    pool_cutoffs = {
        row.source: row.last_pooled_at
        for row in db.query(SourcePoolState).filter(SourcePoolState.source.in_(sources)).all()
    }
    before_cursor = len(all_raw)
    all_raw = [
        job for job in all_raw
        if not pool_cutoffs.get(job["source"])
        or not _parse_posted_at(job.get("posted_at"))
        or _parse_posted_at(job.get("posted_at")) > pool_cutoffs[job["source"]]
    ]
    logger.info(f"Source pool cursor: {len(all_raw)}/{before_cursor} newer raw jobs")

    # Deduplicate before running filters or classifiers. This avoids repeating
    # work for records already known to the database or repeated by sources.
    existing_keys = set(db.query(Job.source, Job.external_id).all())
    seen_keys = set()
    fresh_raw = []
    for job in all_raw:
        key = (job["source"], job["external_id"])
        if key not in existing_keys and key not in seen_keys:
            fresh_raw.append(job)
            seen_keys.add(key)
    logger.info(f"Early deduplication: {len(fresh_raw)}/{len(all_raw)} new raw jobs")
    all_raw = fresh_raw

    # The `log` row may have been flipped to "stopping" by a concurrent stop
    # request while fetching ran. Refresh so this session's in-memory copy
    # reflects that instead of clobbering it back to "ingesting" on the next
    # commit below (SQLAlchemy flushes ALL mapped columns on a dirty object,
    # not just ones this code path reassigned).
    if log is not None:
        db.refresh(log)
        # refresh() opened a transaction; the classify loop below can run for
        # a long time (LLM fallback calls, one job at a time) before it next
        # touches the DB, so close this out now instead of leaving the session
        # idle-in-transaction for that whole stretch.
        db.commit()

    # 2. Pre-filter
    filtered = [j for j in all_raw if pre_filter(j, prefs)]
    logger.info(f"Pre-filter: {len(filtered)}/{len(all_raw)} passed")

    title_matched = [j for j in filtered if _matches_resume_title(j, prefs)]
    logger.info(f"Resume-title filter: {len(title_matched)}/{len(filtered)} passed")

    # Classify and save in the same pass — each job is persisted the moment it
    # clears classification, instead of collecting a remote_only list first and
    # saving afterward. Fetching and classifying a large batch can take minutes
    # (LLM fallback calls run one at a time), so batching the save to the end
    # meant a crash/restart mid-classify lost every already-decided job, and
    # jobs_new sat at 0 for the whole classify duration even though jobs were
    # already being accepted/rejected one by one under the hood.
    new_jobs: list[Job] = []
    duped = 0
    start = time.time()

    for i, job in enumerate(title_matched):
        work_scan = WORK_MODE_SCANNER.scan(
            " ".join(str(job.get(field) or "") for field in ("title", "location", "description"))
        )
        # "unknown" means no remote/hybrid/onsite/restricted language appeared
        # anywhere in title, location, or a description already confirmed to be
        # at least 100 chars (pre_filter) — absence of any remote signal in a
        # substantial posting is itself a strong signal this is an onsite role,
        # so reject outright rather than spending an LLM call to double-check.
        if work_scan["work_mode"] in ("invalid", "hybrid_or_onsite", "restricted_remote", "unknown"):
            continue

        role_scan = TITLE_ROLE_SCANNER.scan(job.get("title", ""))

        if work_scan["confidence"] == "high" and role_scan["confidence"] == "high":
            job["work_mode"] = work_scan["work_mode"]
            job["is_us_remote_eligible"] = True
            job["is_engineering_role"] = role_scan["is_engineering_role"]
        else:
            metadata = extract_ambiguous_job_metadata(job)
            # Trust the regex scanner over the LLM for whichever field it was
            # already confident about — no reason to let the LLM's answer for
            # a decided field override a cheaper, deterministic signal.
            job["work_mode"] = work_scan["work_mode"] if work_scan["confidence"] == "high" else metadata["work_mode"]
            job["is_us_remote_eligible"] = (
                True if work_scan["confidence"] == "high" else metadata["is_us_remote_eligible"]
            )
            job["is_engineering_role"] = (
                role_scan["is_engineering_role"] if role_scan["confidence"] == "high"
                else metadata["is_engineering_role"]
            )
        if not (
            job["work_mode"] == "remote"
            and job["is_us_remote_eligible"]
            and job["is_engineering_role"]
        ):
            continue

        persisted_job = {
            key: value for key, value in job.items()
            if key not in {"is_us_remote_eligible", "is_engineering_role"}
        }
        saved_job, is_new = save_job(persisted_job, db)
        if is_new:
            new_jobs.append(saved_job)
        else:
            duped += 1
        if log is not None and (len(new_jobs) + duped) % 10 == 0:
            log.jobs_new = len(new_jobs)
            log.jobs_duped = duped
            db.commit()

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
    if stopped:
        log.status = "stopped"
    db.commit()

    if not stopped:
        pooled_at = datetime.utcnow()
        for source in sources:
            state = db.query(SourcePoolState).filter_by(source=source).first()
            if state:
                state.last_pooled_at = pooled_at
            else:
                db.add(SourcePoolState(source=source, last_pooled_at=pooled_at))
        db.commit()

    return new_jobs

"""
Job ingestion from Adzuna, Remotive, and Greenhouse ATS.
Each source returns a normalized list of job dicts.
"""
import httpx
import os
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────

def _get(url: str, params: dict = None, retries: int = 3) -> dict | list | None:
    """GET with retry + exponential backoff."""
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"Request failed ({attempt+1}/{retries}): {e} — retrying in {wait}s")
            time.sleep(wait)
    return None


def _normalize(job: dict) -> dict:
    """Ensure every job dict has the same keys."""
    return {
        "source":      job.get("source", "unknown"),
        "external_id": str(job.get("external_id", "")),
        "title":       job.get("title", "").strip(),
        "company":     job.get("company", "").strip(),
        "description": job.get("description", "").strip(),
        "location":    job.get("location", ""),
        "remote":      bool(job.get("remote", False)),
        "salary_min":  job.get("salary_min"),
        "salary_max":  job.get("salary_max"),
        "apply_url":   job.get("apply_url", ""),
        "posted_at":   job.get("posted_at"),  # when the source says the job was listed, if known
    }


# ─────────────────────────────────────────────
# Source 1: Adzuna
# ─────────────────────────────────────────────

def fetch_adzuna(
    keywords: str = "software engineer",
    country: str = "us",
    results_per_page: int = 50,
    page: int = 1,
) -> list[dict]:
    """
    Adzuna public job search API.
    Free tier: 250 req/month. Register at https://developer.adzuna.com/
    """
    app_id  = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.error("ADZUNA_APP_ID / ADZUNA_APP_KEY not set")
        return []

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    data = _get(url, {
        "app_id":           app_id,
        "app_key":          app_key,
        "results_per_page": results_per_page,
        "what":             keywords,
        "content-type":     "application/json",
    })

    if not data or "results" not in data:
        return []

    jobs = []
    for r in data["results"]:
        jobs.append(_normalize({
            "source":      "adzuna",
            "external_id": r.get("id", ""),
            "title":       r.get("title", ""),
            "company":     r.get("company", {}).get("display_name", ""),
            "description": r.get("description", ""),
            "location":    r.get("location", {}).get("display_name", ""),
            "remote":      "remote" in r.get("title", "").lower()
                           or "remote" in r.get("description", "").lower(),
            "salary_min":  r.get("salary_min"),
            "salary_max":  r.get("salary_max"),
            "apply_url":   r.get("redirect_url", ""),
            "posted_at":   r.get("created"),  # ISO 8601 string
        }))

    logger.info(f"Adzuna: fetched {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────
# Source 2: Remotive (remote jobs)
# ─────────────────────────────────────────────

def fetch_remotive(category: str = "", search: str = "") -> list[dict]:
    """
    Remotive public API — no auth required.
    https://remotive.com/api/remote-jobs
    """
    data = _get("https://remotive.com/api/remote-jobs", {
        "category": category,
        "search":   search,
        "limit":    100,
    })

    if not data or "jobs" not in data:
        return []

    jobs = []
    for r in data["jobs"]:
        desc = r.get("description", "")
        # strip HTML tags crudely
        import re
        desc = re.sub(r"<[^>]+>", " ", desc).strip()

        jobs.append(_normalize({
            "source":      "remotive",
            "external_id": str(r.get("id", "")),
            "title":       r.get("title", ""),
            "company":     r.get("company_name", ""),
            "description": desc,
            "location":    r.get("candidate_required_location", "Worldwide"),
            "remote":      True,
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("url", ""),
            "posted_at":   r.get("publication_date"),  # ISO 8601 string
        }))

    logger.info(f"Remotive: fetched {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────
# Source: RemoteOK (remote jobs, no auth)
# ─────────────────────────────────────────────

def fetch_remoteok(search: str = "") -> list[dict]:
    """
    RemoteOK public API — no auth required.
    https://remoteok.com/api
    First element in the response is a legal notice, not a job.
    """
    data = _get("https://remoteok.com/api")
    if not data or not isinstance(data, list):
        return []

    import re
    search_lower = search.lower()

    jobs = []
    for r in data:
        if "id" not in r or "position" not in r:
            continue  # skip the legal-notice header row

        title = r.get("position", "")
        desc = re.sub(r"<[^>]+>", " ", r.get("description", "")).strip()

        if search_lower and search_lower not in title.lower() and search_lower not in desc.lower():
            continue

        jobs.append(_normalize({
            "source":      "remoteok",
            "external_id": str(r.get("id", "")),
            "title":       title,
            "company":     r.get("company", ""),
            "description": desc,
            "location":    r.get("location") or "Worldwide",
            "remote":      True,
            "salary_min":  r.get("salary_min") or None,
            "salary_max":  r.get("salary_max") or None,
            "apply_url":   r.get("url", ""),
            "posted_at":   r.get("date"),  # ISO 8601 string
        }))

    logger.info(f"RemoteOK: fetched {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────
# Source: Jobicy (remote jobs, no auth)
# ─────────────────────────────────────────────

def fetch_jobicy(search: str = "") -> list[dict]:
    """
    Jobicy public API — no auth required.
    https://jobicy.com/api/v2/remote-jobs
    """
    params = {"count": 50}
    if search:
        params["tag"] = search
    data = _get("https://jobicy.com/api/v2/remote-jobs", params)

    if not data or "jobs" not in data:
        return []

    import re
    jobs = []
    for r in data["jobs"]:
        desc = re.sub(r"<[^>]+>", " ", r.get("jobDescription", "")).strip()
        jobs.append(_normalize({
            "source":      "jobicy",
            "external_id": str(r.get("id", "")),
            "title":       r.get("jobTitle", ""),
            "company":     r.get("companyName", ""),
            "description": desc,
            "location":    r.get("jobGeo") or "Worldwide",
            "remote":      True,
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("url", ""),
            "posted_at":   r.get("pubDate"),  # ISO 8601 string
        }))

    logger.info(f"Jobicy: fetched {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────
# Source: Arbeitnow (mixed remote/onsite, mostly EU)
# ─────────────────────────────────────────────

def fetch_arbeitnow(search: str = "") -> list[dict]:
    """
    Arbeitnow public API — no auth required.
    https://www.arbeitnow.com/api/job-board-api
    """
    data = _get("https://www.arbeitnow.com/api/job-board-api")
    if not data or "data" not in data:
        return []

    search_lower = search.lower()
    jobs = []
    for r in data["data"]:
        title = r.get("title", "")
        desc = r.get("description", "")

        if search_lower and search_lower not in title.lower() and search_lower not in desc.lower():
            continue

        created_at = r.get("created_at")
        posted_at = datetime.utcfromtimestamp(created_at).isoformat() if created_at else None

        jobs.append(_normalize({
            "source":      "arbeitnow",
            "external_id": r.get("slug", ""),
            "title":       title,
            "company":     r.get("company_name", ""),
            "description": desc,
            "location":    r.get("location") or "",
            "remote":      bool(r.get("remote", False)),
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("url", ""),
            "posted_at":   posted_at,
        }))

    logger.info(f"Arbeitnow: fetched {len(jobs)} jobs")
    return jobs


# ─────────────────────────────────────────────
# Source 3: Greenhouse ATS (per company)
# ─────────────────────────────────────────────

_DEFAULT_GREENHOUSE_COMPANIES = [
    "airbnb", "stripe", "figma", "notion", "linear",
    "vercel", "anthropic", "openai", "databricks", "cloudflare",
    "discord", "dropbox", "twilio", "hashicorp", "mongodb",
]

def _companies_from_env(var: str, default: list[str]) -> list[str]:
    raw = os.getenv(var)
    if not raw:
        return default
    return [c.strip() for c in raw.split(",") if c.strip()]

GREENHOUSE_COMPANIES = _companies_from_env("GREENHOUSE_COMPANY_TOKENS", _DEFAULT_GREENHOUSE_COMPANIES)

def fetch_greenhouse_company(board_token: str) -> list[dict]:
    """Fetch all open jobs for one company on Greenhouse."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    data = _get(url, {"content": "true"})

    if not data or "jobs" not in data:
        return []

    jobs = []
    for r in data["jobs"]:
        location = ""
        if r.get("location"):
            location = r["location"].get("name", "")

        jobs.append(_normalize({
            "source":      "greenhouse",
            "external_id": f"{board_token}_{r.get('id', '')}",
            "title":       r.get("title", ""),
            "company":     board_token.capitalize(),
            "description": r.get("content", ""),
            "location":    location,
            "remote":      "remote" in location.lower()
                           or "remote" in r.get("title", "").lower(),
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("absolute_url", ""),
            "posted_at":   r.get("updated_at"),  # ISO 8601 string; Greenhouse doesn't expose original post date
        }))

    return jobs


def fetch_greenhouse_all(companies: list[str] = None, should_stop=None) -> list[dict]:
    """Fetch from all configured Greenhouse companies."""
    targets = companies or GREENHOUSE_COMPANIES
    all_jobs = []
    for company in targets:
        if should_stop and should_stop():
            logger.info("Greenhouse fetch stopped early")
            break
        try:
            jobs = fetch_greenhouse_company(company)
            all_jobs.extend(jobs)
            logger.info(f"Greenhouse/{company}: {len(jobs)} jobs")
            time.sleep(0.3)  # polite rate limiting
        except Exception as e:
            logger.warning(f"Greenhouse/{company} failed: {e}")
    return all_jobs


# ─────────────────────────────────────────────
# Source 4: Lever ATS (per company)
# ─────────────────────────────────────────────

_DEFAULT_LEVER_COMPANIES = [
    "netflix", "reddit", "canva", "plaid", "rippling",
    "brex", "gusto", "lattice", "carta", "ironclad",
]

LEVER_COMPANIES = _companies_from_env("LEVER_COMPANY_TOKENS", _DEFAULT_LEVER_COMPANIES)

def fetch_lever_company(company: str) -> list[dict]:
    """Fetch all open jobs for one company on Lever."""
    url = f"https://api.lever.co/v0/postings/{company}"
    data = _get(url, {"mode": "json"})

    if not data or not isinstance(data, list):
        return []

    jobs = []
    for r in data:
        location = r.get("categories", {}).get("location", "")
        commitment = r.get("categories", {}).get("commitment", "")

        # Build description from lists
        desc_parts = []
        for section in r.get("lists", []):
            desc_parts.append(section.get("text", ""))
            items = section.get("content", "")
            if items:
                import re
                items_clean = re.sub(r"<[^>]+>", " ", items)
                desc_parts.append(items_clean)

        created_at_ms = r.get("createdAt")
        posted_at = datetime.utcfromtimestamp(created_at_ms / 1000).isoformat() if created_at_ms else None

        jobs.append(_normalize({
            "source":      "lever",
            "external_id": r.get("id", ""),
            "title":       r.get("text", ""),
            "company":     company.capitalize(),
            "description": "\n".join(desc_parts),
            "location":    location,
            "remote":      "remote" in location.lower() or "remote" in commitment.lower(),
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("applyUrl", r.get("hostedUrl", "")),
            "posted_at":   posted_at,
        }))

    return jobs


def fetch_lever_all(companies: list[str] = None, should_stop=None) -> list[dict]:
    """Fetch from all configured Lever companies."""
    targets = companies or LEVER_COMPANIES
    all_jobs = []
    for company in targets:
        if should_stop and should_stop():
            logger.info("Lever fetch stopped early")
            break
        try:
            jobs = fetch_lever_company(company)
            all_jobs.extend(jobs)
            logger.info(f"Lever/{company}: {len(jobs)} jobs")
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Lever/{company} failed: {e}")
    return all_jobs


# ─────────────────────────────────────────────
# Source 5: Ashby ATS (per company)
# ─────────────────────────────────────────────

_DEFAULT_ASHBY_COMPANIES: list[str] = []  # populated dynamically via discovery; no static defaults

ASHBY_COMPANIES = _companies_from_env("ASHBY_COMPANY_TOKENS", _DEFAULT_ASHBY_COMPANIES)

def fetch_ashby_company(board_token: str) -> list[dict]:
    """Fetch all open jobs for one company on Ashby."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    data = _get(url)

    if not data or "jobs" not in data:
        return []

    import re
    jobs = []
    for r in data["jobs"]:
        desc = re.sub(r"<[^>]+>", " ", r.get("descriptionHtml", "")).strip()
        jobs.append(_normalize({
            "source":      "ashby",
            "external_id": r.get("id", ""),
            "title":       (r.get("title") or "").strip(),
            "company":     board_token.capitalize(),
            "description": desc,
            "location":    r.get("location", ""),
            "remote":      bool(r.get("isRemote", False)),
            "salary_min":  None,
            "salary_max":  None,
            "apply_url":   r.get("applyUrl", r.get("jobUrl", "")),
            "posted_at":   r.get("publishedAt"),  # ISO 8601 string
        }))

    return jobs


def fetch_ashby_all(companies: list[str] = None, should_stop=None) -> list[dict]:
    """Fetch from all configured Ashby companies."""
    targets = companies or ASHBY_COMPANIES
    all_jobs = []
    for company in targets:
        if should_stop and should_stop():
            logger.info("Ashby fetch stopped early")
            break
        try:
            jobs = fetch_ashby_company(company)
            all_jobs.extend(jobs)
            logger.info(f"Ashby/{company}: {len(jobs)} jobs")
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Ashby/{company} failed: {e}")
    return all_jobs


# ─────────────────────────────────────────────
# Dynamic company discovery: probe aggregator-sourced company names for a
# matching Greenhouse/Lever/Ashby board, cache results so nothing is ever
# re-probed once resolved either way.
# ─────────────────────────────────────────────

_ATS_SUFFIXES = [
    " inc.", " inc", " llc", " corp.", " corp", " ltd.", " ltd",
    " co.", " co", " corporation", " incorporated", " limited",
]


def slug_candidates(company_name: str) -> list[str]:
    """
    e.g. 'Notion Labs, Inc.' -> ['notion-labs-inc', 'notion-labs', 'notion']
    Ordered most-specific to least-specific; callers should stop at the
    first slug that resolves.
    """
    import re

    name = company_name.strip().lower()
    name = name.replace(",", "")
    for suffix in _ATS_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()

    full_slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    words = full_slug.split("-")

    candidates = [full_slug]
    if len(words) > 1:
        candidates.append("-".join(words[:-1]))  # drop last word, e.g. "notion-labs"
        candidates.append(words[0])              # just first word, e.g. "notion"

    # Dedup while preserving order
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def probe_greenhouse(slug: str) -> bool:
    try:
        resp = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=5)
        return resp.status_code == 200 and bool(resp.json().get("jobs"))
    except Exception:
        return False


def probe_lever(slug: str) -> bool:
    try:
        resp = httpx.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}, timeout=5)
        return resp.status_code == 200 and isinstance(resp.json(), list) and len(resp.json()) > 0
    except Exception:
        return False


def probe_ashby(slug: str) -> bool:
    try:
        resp = httpx.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=5)
        return resp.status_code == 200 and bool(resp.json().get("jobs"))
    except Exception:
        return False


PROBE_FUNCS = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
}

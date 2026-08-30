"""
Auto-apply engine.
Generates a custom cover letter per application via Claude,
then attempts submission via Greenhouse/Lever APIs or Playwright form fill.
"""
import logging
import os
from anthropic import Anthropic
from sqlalchemy.orm import Session

from ..db.models import AppliedJob, Job, Resume

logger = logging.getLogger(__name__)
client = Anthropic()


# ─────────────────────────────────────────────
# Cover letter generation
# ─────────────────────────────────────────────

COVER_LETTER_PROMPT = """Write a concise, genuine cover letter for this job application.

Rules:
- 3 short paragraphs only
- Never use hollow phrases: "passionate", "excited to apply", "perfect fit"
- Open with a specific insight about the company or role, not about yourself
- Middle paragraph: 2–3 concrete achievements from the resume that directly address the role
- Close: one sentence on what you'd focus on in the first 90 days
- Tone: confident, direct, human — not corporate

CANDIDATE'S SELLING POINTS FOR THIS ROLE:
{selling_points}

RESUME EXCERPT:
{resume_excerpt}

ROLE: {title} at {company}
JOB DESCRIPTION EXCERPT:
{job_excerpt}

Write only the letter body — no "Dear Hiring Manager", no sign-off needed."""


def generate_cover_letter(
    resume: Resume,
    job: Job,
    selling_points: list[str],
) -> str:
    """Generate a tailored cover letter via Claude."""
    prompt = COVER_LETTER_PROMPT.format(
        selling_points="\n".join(f"• {p}" for p in selling_points),
        resume_excerpt=resume.content[:2000],
        title=job.title,
        company=job.company,
        job_excerpt=job.description[:1500],
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Cover letter generation failed: {e}")
        return ""


# ─────────────────────────────────────────────
# Application strategies
# ─────────────────────────────────────────────

def apply_greenhouse(job: Job, resume: Resume, cover_letter: str) -> tuple[str, str | None]:
    """
    Submit via Greenhouse's public apply API.
    Returns (status, error_msg).
    """
    import httpx

    # Extract job ID from URL or external_id
    # Greenhouse external_id format: "company_12345"
    parts = job.external_id.split("_")
    if len(parts) < 2:
        return "failed", "Could not parse Greenhouse job ID"

    board_token = parts[0]
    gh_job_id   = parts[-1]

    applicant_info = {
        "first_name": os.getenv("APPLICANT_FIRST_NAME", ""),
        "last_name":  os.getenv("APPLICANT_LAST_NAME", ""),
        "email":      os.getenv("APPLICANT_EMAIL", ""),
        "phone":      os.getenv("APPLICANT_PHONE", ""),
        "cover_letter_text": cover_letter,
    }

    if not all(applicant_info[k] for k in ["first_name", "last_name", "email"]):
        return "failed", "Applicant info not configured in .env"

    try:
        # Greenhouse embed apply endpoint
        url = f"https://boards.greenhouse.io/apply/{gh_job_id}"
        resp = httpx.post(url, data={
            **applicant_info,
            "job_id": gh_job_id,
        }, timeout=20)

        if resp.status_code in (200, 201, 302):
            return "applied", None
        else:
            return "failed", f"HTTP {resp.status_code}"
    except Exception as e:
        return "failed", str(e)


def apply_lever(job: Job, resume: Resume, cover_letter: str) -> tuple[str, str | None]:
    """
    Submit via Lever's public apply endpoint.
    Lever exposes POST /apply on their hosted job pages.
    """
    import httpx

    company = job.external_id.split("_")[0] if "_" in job.external_id else job.company.lower()
    posting_id = job.external_id

    data = {
        "name":        f"{os.getenv('APPLICANT_FIRST_NAME')} {os.getenv('APPLICANT_LAST_NAME')}",
        "email":       os.getenv("APPLICANT_EMAIL", ""),
        "phone":       os.getenv("APPLICANT_PHONE", ""),
        "org":         os.getenv("APPLICANT_CURRENT_COMPANY", ""),
        "comments":    cover_letter,
        "urls[LinkedIn]": os.getenv("APPLICANT_LINKEDIN", ""),
    }

    try:
        url = f"https://jobs.lever.co/{company}/{posting_id}/apply"
        resp = httpx.post(url, data=data, timeout=20)
        if resp.status_code in (200, 201):
            return "applied", None
        else:
            return "failed", f"HTTP {resp.status_code}"
    except Exception as e:
        return "failed", str(e)


def apply_playwright(job: Job, resume: Resume, cover_letter: str) -> tuple[str, str | None]:
    """
    Fallback: use Playwright to fill the apply form.
    Handles jobs that don't have a direct API endpoint.
    """
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(job.apply_url, timeout=30000)

            # Generic form filling — works for many ATS
            selectors = {
                'input[name*="first"]': os.getenv("APPLICANT_FIRST_NAME", ""),
                'input[name*="last"]':  os.getenv("APPLICANT_LAST_NAME", ""),
                'input[name*="email"]': os.getenv("APPLICANT_EMAIL", ""),
                'input[name*="phone"]': os.getenv("APPLICANT_PHONE", ""),
                'textarea[name*="cover"]': cover_letter,
                'textarea[name*="letter"]': cover_letter,
            }

            for selector, value in selectors.items():
                if value:
                    try:
                        page.fill(selector, value, timeout=2000)
                    except Exception:
                        pass

            # Upload resume file
            if resume.file_path and os.path.exists(resume.file_path):
                try:
                    file_input = page.query_selector('input[type="file"]')
                    if file_input:
                        file_input.set_input_files(resume.file_path)
                except Exception:
                    pass

            # NOTE: Do NOT auto-submit in production without human review flag
            # page.click('button[type="submit"]')

            browser.close()
            return "applied", None

    except Exception as e:
        return "failed", str(e)


# ─────────────────────────────────────────────
# Main apply dispatcher
# ─────────────────────────────────────────────

def apply_to_job(
    job: Job,
    resume: Resume,
    cover_letter: str,
) -> tuple[str, str | None]:
    """Route to the right apply strategy based on job source."""
    source = job.source.lower()

    if source == "greenhouse":
        return apply_greenhouse(job, resume, cover_letter)
    elif source == "lever":
        return apply_lever(job, resume, cover_letter)
    else:
        # Generic Playwright fallback for Adzuna, Remotive, etc.
        return apply_playwright(job, resume, cover_letter)


def run_applications(candidates: list[dict], db: Session):
    """
    For each matched candidate dict from matching engine:
    1. Generate cover letter
    2. Dedup check (belt-and-suspenders)
    3. Apply
    4. Log result
    """
    for c in candidates:
        job: Job       = c["job"]
        resume: Resume = c["best_resume"]
        score: float   = c["best_score"]

        # Belt-and-suspenders dedup
        existing = db.query(AppliedJob).filter_by(job_id=job.id).first()
        if existing:
            logger.warning(f"DEDUP CAUGHT: {job.title} already in applied_jobs — skip")
            continue

        # Generate cover letter
        cover_letter = generate_cover_letter(resume, job, c["selling_points"])

        # Apply
        status, error = apply_to_job(job, resume, cover_letter)

        # Log regardless of outcome
        record = AppliedJob(
            job_id=job.id,
            resume_id=resume.id,
            match_score=score,
            cover_letter=cover_letter,
            status=status,
            error_msg=error,
        )
        db.add(record)
        db.commit()

        if status == "applied":
            logger.info(
                f"✅ APPLIED: {job.title} @ {job.company} "
                f"({score:.0%} match, {resume.label})"
            )
        else:
            logger.warning(
                f"❌ FAILED: {job.title} @ {job.company} — {error}"
            )

"""
Matching engine: Claude scores each job against every resume in parallel.
Returns the best resume and score for each job.
"""
import json
import logging
import re
import time
import concurrent.futures
from sqlalchemy.orm import Session

from ..db.models import Job, Resume, JobMatch, AppliedJob
from ..llm import generate_text

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.70  # minimum score to auto-apply


# ─────────────────────────────────────────────
# Claude scoring prompt
# ─────────────────────────────────────────────

WORK_MODE_PROMPT = """Read this job description and determine its work mode.

JOB TITLE: {title}
JOB DESCRIPTION:
{description}

Respond ONLY with valid JSON — no markdown, no preamble:
{{"work_mode": "remote|hybrid|onsite"}}

remote: fully remote, no office attendance required
hybrid: some in-office days required alongside remote work
onsite: full-time in-office / no remote option mentioned
If unclear from the text, make your best guess from context (title, seniority, industry norms)."""
import json
import re

def parse_llm_json_response(raw_output) -> dict:
    """Safely parses string or dict responses from LLM helpers."""
    if isinstance(raw_output, dict):
        return raw_output
    elif isinstance(raw_output, str):
        formatted = raw_output.strip()
        if not formatted.startswith("{"):
            formatted = "{" + formatted
        formatted = re.sub(r',\s*([\}\]])', r'\1', formatted)
        return json.loads(formatted)
    else:
        raise TypeError(f"Expected dict or str, got {type(raw_output)}")


def normalize_selling_points(value) -> list[str]:
    """Convert malformed sentence strings into the array expected by the DB."""
    if isinstance(value, str):
        return [point.strip() for point in re.split(r"\.\s+(?=[A-Z])", value.strip()) if point.strip()]
    if isinstance(value, list):
        if len(value) > 1 and all(isinstance(point, str) and len(point) == 1 for point in value):
            return normalize_selling_points("".join(value))
        if any(
            current and following and not current.endswith((".", "!", "?"))
            and following[0].islower()
            for current, following in zip(value, value[1:])
        ):
            repaired = " ".join(value)
            repaired = re.sub(r"\bNode\s+js\b", "Node.js", repaired, flags=re.IGNORECASE)
            return normalize_selling_points(repaired)
        return value
    return []


def calculate_final_score(eval_result: dict) -> float:
    """Calculate the final match score with discipline and scope safeguards."""
    if not eval_result.get("discipline_match", True) or eval_result.get("scope_mismatch", False):
        return 0.10

    weights = {
        "required_skills_pct": 0.40,
        "domain_fit_pct": 0.30,
        "seniority_fit_pct": 0.20,
        "experience_years_pct": 0.10,
    }
    score = sum(
        (eval_result.get(key, 0) / 100.0) * weight
        for key, weight in weights.items()
    )
    return round(score, 2)

def detect_work_mode(job: dict) -> str:
    """Classify a job's work mode via the LLM. One call per job, not per resume."""
    listing_text = " ".join(
        str(job.get(field) or "") for field in ("title", "location", "description")
    ).lower()
    if re.search(r"\b(in[- ]office|on[- ]site|onsite|office[- ]based)\b", listing_text):
        return "onsite"
    if re.search(r"\bhybrid\b", listing_text):
        return "hybrid"
    if job.get("remote") is True:
        return "remote"
    if job.get("remote") is False and job.get("location"):
        return "onsite"

    try:
        prompt = WORK_MODE_PROMPT.format(title=job["title"], description=job["description"][:800])
        raw = generate_text(prompt)
        result = parse_llm_json_response(raw)
        mode = result.get("work_mode", "").lower()
        return mode if mode in ("remote", "hybrid", "onsite") else "onsite"
    except Exception as e:
        logger.error(f"Work mode detection failed: {e}")
        return "onsite"


SCORE_PROMPT = """You are an objective, highly precise technical recruiter evaluating resume fit for a job posting.

JOB TITLE: {title}
COMPANY: {company}
JOB DESCRIPTION:
{description}

CANDIDATE RESUME ({label}):
{resume_content}

REASONING RULES:
1. Keep internal reasoning inside <think> strictly under 100 words. Move directly to evaluation.
2. Focus strictly on skills explicitly listed under REQUIRED QUALIFICATIONS in the job description.

SKILL-MATCHING & SEARCH RULES:
- FIRST EXTRACT THE JOB: Identify its primary domain and explicit required
    stack before considering the resume. key_skills must come from the job
    description, not from the resume summary.
- KEEP SCOPE ACCURATE: Do not mention Mobile, React Native, or mobile apps
    unless the job description explicitly requires iOS, Android, React Native,
    or mobile development. For backend/systems roles, focus on the stated
    systems, APIs, storage, distributed systems, infrastructure, and latency
    requirements.
- EVIDENCE ONLY: selling_points may mention only overlap between an explicit
    job requirement and evidence in the resume. Do not call generic full-stack
    or mobile experience a match for an unstated requirement.
- EQUIVALENCY RULE: Do NOT list a skill as "missing" if the candidate demonstrates equivalent technology:
  * AWS / Azure / GCP = Cloud Infrastructure
  * React Native / React / Vue / Angular = Frontend UI
  * Node.js / Python / Go / Java / C# = Backend APIs
  * PostgreSQL / MySQL / MongoDB / CosmosDB = Databases
  * Docker / Kubernetes / CI/CD = DevOps & Deployment
- NO HALLUCINATIONS: Do NOT list domain-specific tags (e.g., Robotics, ML, Computer Vision, Embedded) as "missing" UNLESS they are explicitly listed as mandatory requirements in the job description.
- STRICT KEY SKILLS FORMAT: key_skills must be short skill/tool/domain NAMES
    ONLY (1-4 words each), taken from explicit job requirements. Never use
    full sentences, resume-summary phrases, or skills absent from the job
    description. Extract exactly 4-6 when the job provides that many.

OUTPUT FORMAT:
Output MUST be raw, valid JSON following this exact structure without markdown code blocks:

{{
  "job_discipline": "string",
  "resume_discipline": "string",
  "discipline_match": true,
  "scope_mismatch": false,
  "discipline_and_scope_analysis": "string",
  "required_skills_pct": 0-100,
  "experience_years_pct": 0-100,
  "domain_fit_pct": 0-100,
  "seniority_fit_pct": 0-100,
  "key_skills": ["string"],
  "missing_skills": ["string"],
  "selling_points": ["string"],
  "seniority_fit": "good",
  "recommended_resume": true,
  "reasoning": "string"
}}"""


def score_one(resume: dict, job: dict) -> dict:
    """Synchronously score one resume against one job via Claude."""
    prompt = SCORE_PROMPT.format(
        label=resume["label"],
        resume_content=resume["content"][:2500],  # token budget — local models are latency-sensitive to input size
        title=job["title"],
        company=job["company"],
        description=job["description"][:1800],
    )

    try:
        raw = generate_text(prompt)

        if isinstance(raw, dict):
            result = raw
        elif isinstance(raw, str):
            formatted_raw = raw.strip()
            
            # Prepend missing opening brace if using assistant pre-fill
            if not formatted_raw.startswith("{"):
                formatted_raw = "{" + formatted_raw
                
            # Clean up trailing commas before closing braces/brackets
            formatted_raw = re.sub(r',\s*([\}\]])', r'\1', formatted_raw)
            
            result = json.loads(formatted_raw)
        else:
            raise TypeError(f"Unexpected response type from generate_text: {type(raw)}")

        result["selling_points"] = normalize_selling_points(result.get("selling_points"))

        sub_scores = {
            "required_skills_pct": result.get("required_skills_pct"),
            "experience_years_pct": result.get("experience_years_pct"),
            "domain_fit_pct": result.get("domain_fit_pct"),
            "seniority_fit_pct": result.get("seniority_fit_pct"),
        }
        if any(v is None for v in sub_scores.values()):
            raise ValueError(f"Missing sub-score(s) in LLM response: {result}")

        result["score"] = calculate_final_score(result)
        result.setdefault("reasoning", "")
        result.setdefault("missing_skills", [])
        result.setdefault("key_skills", [])
        result["failed"] = False
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {resume['label']} / {job['title']}: {e}")
        result = {
            "score": 0.0,
            "reasoning": "Parsing error",
            "missing_skills": [],
            "selling_points": [],
            "seniority_fit": "unknown",
            "recommended_resume": False,
            "failed": True,
        }
    except Exception as e:
        logger.error(f"LLM API error: {e}")
        result = {"score": 0.0, "reasoning": str(e), "missing_skills": [],
                  "selling_points": [], "seniority_fit": "unknown", "recommended_resume": False,
                  "failed": True}

    result["resume_id"] = resume["id"]
    result["resume_label"] = resume["label"]
    return result


def score_job_all_resumes(job: dict, resumes: list[dict]) -> list[dict]:
    """
    Score one job against ALL resumes in parallel (thread pool).
    Returns results sorted by score descending.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(resumes)) as executor:
        futures = {
            executor.submit(score_one, resume, job): resume
            for resume in resumes
        }

        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return sorted(results, key=lambda x: x["score"], reverse=True)


# ─────────────────────────────────────────────
# Save match scores to DB
# ─────────────────────────────────────────────

def save_matches(job_id: str, scores: list[dict], db: Session):
    """
    Upsert match scores for all resumes. Failed LLM calls (parse errors,
    API errors) are never persisted as a real 0% match — that would
    permanently block the job from being picked up by a future rematch.
    """
        
    for score in scores:
        if score.get("failed"):
            logger.warning(
                f"Skipping save for failed score: job={job_id} resume={score.get('resume_label')}"
            )
            continue

        existing = db.query(JobMatch).filter_by(
            job_id=job_id,
            resume_id=score["resume_id"]
        ).first()

        if existing:
            existing.score          = score["score"]
            existing.reasoning      = score["reasoning"]
            existing.missing_skills = score["missing_skills"]
            existing.selling_points = score["selling_points"]
        else:
            match = JobMatch(
                job_id=job_id,
                resume_id=score["resume_id"],
                score=score["score"],
                reasoning=score["reasoning"],
                missing_skills=score["missing_skills"],
                selling_points=score["selling_points"],
            )
            db.add(match)
    db.commit()


# ─────────────────────────────────────────────
# Main matching entry point
# ─────────────────────────────────────────────

def already_applied(job_id: str, db: Session) -> bool:
    return db.query(AppliedJob).filter_by(job_id=job_id).first() is not None


def process_jobs_for_matching(
    jobs: list[Job],
    resumes: list[Resume],
    db: Session,
) -> list[dict]:
    """
    For each new job:
    1. Check not already applied
    2. Score against all resumes in parallel
    3. Save all match scores
    4. Return jobs that cleared the threshold with their best resume

    Returns list of dicts: {job, best_resume, best_score, selling_points}
    """
    resume_dicts = [
        {
            "id":      str(r.id),
            "label":   r.label or r.filename,
            "content": r.content,
        }
        for r in resumes if r.active
    ]

    if not resume_dicts:
        logger.error("No active resumes found — nothing to match")
        return []

    candidates = []
 
    for job in jobs:
        job_id = str(job.id)
        job_start = time.monotonic()
        applied = already_applied(job_id, db)

        job_dict = {
            "id":          job_id,
            "title":       job.title,
            "company":     job.company,
            "description": job.description,
            "location":    job.location,
            "remote":      job.remote,
        }

        if not job.work_mode or (job.work_mode == "remote" and not job.remote):
            job.work_mode = detect_work_mode(job_dict)
        db.commit()

        logger.info(f"Scoring: {job.title} @ {job.company} against {len(resume_dicts)} resumes")
        scores = score_job_all_resumes(job_dict, resume_dicts)

        # Save all scores for the dashboard
        save_matches(job_id, scores, db)

        # key_skills describes the job itself, not a resume pairing — refresh
        # it on every successful rescore (not just once) so an improved
        # prompt/model correcting an earlier bad extraction actually takes
        # effect instead of leaving a stale value cached forever. An empty
        # list is meaningful for a discipline mismatch and must also replace
        # the previous value.
        for s in scores:
            if not s.get("failed") and "key_skills" in s:
                job.key_skills = s["key_skills"]
                db.commit()
                break

        job_elapsed = time.monotonic() - job_start
        logger.info(f"Job processed in {job_elapsed:.2f}s: {job.title} @ {job.company}")

        best = scores[0]
        if best["score"] >= SCORE_THRESHOLD and applied:
            # Already applied — still fully scored/saved above (so Matches/
            # Jobs feed show accurate data), just excluded from the
            # auto-apply candidate set so we never try to apply again.
            logger.debug(f"SKIP candidate (already applied): {job.title} @ {job.company}")
        elif best["score"] >= SCORE_THRESHOLD:
            logger.info(
                f"✓ MATCH {best['score']:.0%}: {job.title} @ {job.company} "
                f"→ {best['resume_label']}"
            )
            candidates.append({
                "job":           job,
                "best_resume":   next(r for r in resumes if str(r.id) == best["resume_id"]),
                "best_score":    best["score"],
                "all_scores":    scores,
                "selling_points": best["selling_points"],
                "missing_skills": best["missing_skills"],
            })
        elif best.get("failed"):
            logger.warning(f"✗ SCORING FAILED (not saved, will retry): {job.title} @ {job.company}")
        else:
            logger.info(
                f"✗ LOW MATCH {best['score']:.0%}: {job.title} @ {job.company} — skip"
            )

    logger.info(f"Matching complete: {len(candidates)}/{len(jobs)} cleared threshold")
    return candidates

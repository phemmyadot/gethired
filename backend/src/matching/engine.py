"""
Matching engine: Claude scores each job against every resume in parallel.
Returns the best resume and score for each job.
"""
import json
import logging
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


def detect_work_mode(job: dict) -> str:
    """Classify a job's work mode via the LLM. One call per job, not per resume."""
    try:
        prompt = WORK_MODE_PROMPT.format(title=job["title"], description=job["description"][:800])
        raw = generate_text(prompt)
        result = json.loads(raw)
        mode = result.get("work_mode", "").lower()
        return mode if mode in ("remote", "hybrid", "onsite") else "onsite"
    except Exception as e:
        logger.error(f"Work mode detection failed: {e}")
        return "onsite"


SCORE_PROMPT = """You are a senior technical recruiter with 15 years experience.
Evaluate how well this candidate's resume matches the job description.

Score by rating FOUR sub-factors independently on a 0-100 scale, then averaging them.
Do not skip this step or eyeball a final number directly — compute each sub-score first from
concrete evidence in the resume and job description, using the full 0-100 range where warranted:

1. required_skills_pct (0-100): what percentage of the job's explicitly required skills/tools
   does the resume demonstrate? Count them if you can.
2. experience_years_pct (0-100): does the resume show enough relevant years of experience for
   this role? 100 = meets or exceeds, lower = proportional shortfall.
3. domain_fit_pct (0-100): how closely does the resume's domain/industry background match what
   this job needs?
4. seniority_fit_pct (0-100): does the resume's seniority level match the role (not over- or
   under-qualified)?

RESUME LABEL: {label}
RESUME:
{resume_content}

JOB TITLE: {title} at {company}
JOB DESCRIPTION:
{description}

Respond ONLY with valid JSON — no markdown, no preamble:
{{
  "required_skills_pct": <int 0-100>,
  "experience_years_pct": <int 0-100>,
  "domain_fit_pct": <int 0-100>,
  "seniority_fit_pct": <int 0-100>,
  "reasoning": "One paragraph explaining the match quality, citing specific resume/job details and referencing the sub-scores above.",
  "key_skills": ["skill1", "skill2"],
  "missing_skills": ["skill1", "skill2"],
  "selling_points": ["point1", "point2"],
  "seniority_fit": "good|over|under",
  "recommended_resume": true
}}

key_skills: the job posting's own top required skills/tools/technologies, independent of this
  resume (max 6) — this describes what the JOB wants, not how well the candidate matches it
missing_skills: skills in job description not evident in resume (max 5)
selling_points: strongest resume points for this role (max 4)
seniority_fit: is this role a good level match?
recommended_resume: true if this is likely the best resume to use

Do not include a "score" field — it will be computed from your four sub-scores."""


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
        result = json.loads(raw)

        # Compute the score ourselves from the four sub-scores rather than
        # trusting a model-produced float — a directly-generated score is
        # prone to anchoring on whatever example values appear in the
        # prompt (this happened twice: first on a literal example score,
        # then again on a number listed as a "variety" example).
        sub_scores = [
            result.get("required_skills_pct"),
            result.get("experience_years_pct"),
            result.get("domain_fit_pct"),
            result.get("seniority_fit_pct"),
        ]
        if any(s is None for s in sub_scores):
            raise ValueError(f"Missing sub-score(s) in LLM response: {result}")
        result["score"] = round(sum(sub_scores) / len(sub_scores) / 100, 3)
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

        # Dedup guard
        if already_applied(job_id, db):
            logger.debug(f"SKIP (applied): {job.title} @ {job.company}")
            continue

        job_dict = {
            "id":          job_id,
            "title":       job.title,
            "company":     job.company,
            "description": job.description,
        }

        if not job.work_mode:
            job.work_mode = detect_work_mode(job_dict)
            db.commit()

        logger.info(f"Scoring: {job.title} @ {job.company} against {len(resume_dicts)} resumes")
        scores = score_job_all_resumes(job_dict, resume_dicts)

        # Save all scores for the dashboard
        save_matches(job_id, scores, db)

        # key_skills describes the job itself, not a resume pairing — cache
        # it on the Job row the first time any successful score provides it.
        if not job.key_skills:
            for s in scores:
                if not s.get("failed") and s.get("key_skills"):
                    job.key_skills = s["key_skills"]
                    db.commit()
                    break

        job_elapsed = time.monotonic() - job_start
        logger.info(f"Job processed in {job_elapsed:.2f}s: {job.title} @ {job.company}")

        best = scores[0]
        if best["score"] >= SCORE_THRESHOLD:
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

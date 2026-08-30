"""
Matching engine: Claude scores each job against every resume in parallel.
Returns the best resume and score for each job.
"""
import json
import logging
import asyncio
import concurrent.futures
from typing import Optional
from anthropic import Anthropic
from sqlalchemy.orm import Session

from ..db.models import Job, Resume, JobMatch, AppliedJob

logger = logging.getLogger(__name__)
client = Anthropic()

SCORE_THRESHOLD = 0.70  # minimum score to auto-apply


# ─────────────────────────────────────────────
# Claude scoring prompt
# ─────────────────────────────────────────────

SCORE_PROMPT = """You are a senior technical recruiter with 15 years experience.
Evaluate how well this candidate's resume matches the job description.

Be strict and honest. A score of 0.70 means genuinely qualified — not just keyword overlap.
Consider: required skills match, years of experience, domain fit, seniority alignment.

RESUME LABEL: {label}
RESUME:
{resume_content}

JOB TITLE: {title} at {company}
JOB DESCRIPTION:
{description}

Respond ONLY with valid JSON — no markdown, no preamble:
{{
  "score": 0.82,
  "reasoning": "One paragraph explaining the match quality.",
  "missing_skills": ["skill1", "skill2"],
  "selling_points": ["point1", "point2"],
  "seniority_fit": "good|over|under",
  "recommended_resume": true
}}

score: 0.0 to 1.0
missing_skills: skills in job description not evident in resume (max 5)
selling_points: strongest resume points for this role (max 4)
seniority_fit: is this role a good level match?
recommended_resume: true if this is likely the best resume to use"""


def score_one(resume: dict, job: dict) -> dict:
    """Synchronously score one resume against one job via Claude."""
    prompt = SCORE_PROMPT.format(
        label=resume["label"],
        resume_content=resume["content"][:4000],  # token budget
        title=job["title"],
        company=job["company"],
        description=job["description"][:3000],
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {resume['label']} / {job['title']}: {e}")
        result = {
            "score": 0.0,
            "reasoning": "Parsing error",
            "missing_skills": [],
            "selling_points": [],
            "seniority_fit": "unknown",
            "recommended_resume": False,
        }
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        result = {"score": 0.0, "reasoning": str(e), "missing_skills": [],
                  "selling_points": [], "seniority_fit": "unknown", "recommended_resume": False}

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
    """Upsert match scores for all resumes."""
    for score in scores:
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

        logger.info(f"Scoring: {job.title} @ {job.company} against {len(resume_dicts)} resumes")
        scores = score_job_all_resumes(job_dict, resume_dicts)

        # Save all scores for the dashboard
        save_matches(job_id, scores, db)

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
        else:
            logger.info(
                f"✗ LOW MATCH {best['score']:.0%}: {job.title} @ {job.company} — skip"
            )

    logger.info(f"Matching complete: {len(candidates)}/{len(jobs)} cleared threshold")
    return candidates

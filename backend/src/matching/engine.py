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


SCORE_PROMPT = """You are a strict senior technical recruiter. Assume a resume does NOT match
until you find concrete evidence otherwise. A shared buzzword or tool (e.g. both mention "React"
or "Node.js") does NOT mean the candidate is qualified for a different discipline.

First, identify the job's core discipline (e.g. mobile engineering, backend/API engineering, data
engineering, sales, DevOps, ML engineering) and the resume's primary discipline from its actual
work history. If they differ, cap required_skills_pct, domain_fit_pct, AND experience_years_pct
ALL at 25 regardless of any shared tools, languages, or years of seniority — years of experience
in a DIFFERENT discipline do not count toward this role. Only go higher on these three than 25 if
the resume's actual day-to-day work matches the job's actual day-to-day work. Do NOT let a high
seniority_fit_pct or seniority title compensate for a discipline mismatch — a senior mobile
engineer applying to a senior backend role is still a mismatch, just at a senior level.

For required_skills_pct: only count a required skill as demonstrated if the resume shows it was
used hands-on for similar work, not just listed or mentioned in passing. A resume matching 0-1 of
6+ required skills should score 0-15, not 60-80.

Rate FOUR sub-factors on a 0-100 scale:

1. required_skills_pct (0-100): % of the job's explicitly required skills/tools genuinely
   demonstrated in the resume (see rule above).
2. experience_years_pct (0-100): enough relevant years IN THIS DISCIPLINE (not just total years
   in tech)? 100 = meets or exceeds. Capped at 25 if discipline mismatch (see above).
3. domain_fit_pct (0-100): per the discipline check above.
4. seniority_fit_pct (0-100): does seniority LEVEL match (not over/under-qualified)? This is the
   only sub-factor NOT capped by discipline mismatch — it reflects level only.

RESUME LABEL: {label}
RESUME:
{resume_content}

JOB TITLE: {title} at {company}
JOB DESCRIPTION:
{description}

Respond ONLY with valid JSON — no markdown, no preamble:
{{
  "job_discipline": "the job's core discipline, 2-4 words",
  "resume_discipline": "the resume's primary discipline based on actual work history, 2-4 words",
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
missing_skills: skills/tools THE JOB REQUIRES that are NOT present anywhere in the resume (max 5).
  Every entry must be a skill named or clearly implied by the JOB DESCRIPTION. NEVER list a skill
  the resume has just because the job doesn't need it — that is backwards and wrong. Example: if
  the job needs "Web components, Design system" and the resume shows "React Native, Expo" instead,
  missing_skills = ["Web components", "Design system"] — NOT "React Native" or "Expo", since those
  aren't required by the job at all, they're just what the resume happens to have instead.
selling_points: strongest resume points for this role (max 4) — omit if disciplines don't match
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
        #
        # Weighted, not averaged: a flat average let strong experience/domain/
        # seniority scores mask near-zero required-skill overlap (e.g. a
        # mobile engineer scored 75% against a backend API role because only
        # 1 of 4 sub-scores reflected the actual skill mismatch). Required
        # skills now dominate the score so a real skills gap can't be
        # papered over by tenure or adjacent domain experience.
        sub_scores = {
            "required_skills_pct": result.get("required_skills_pct"),
            "experience_years_pct": result.get("experience_years_pct"),
            "domain_fit_pct": result.get("domain_fit_pct"),
            "seniority_fit_pct": result.get("seniority_fit_pct"),
        }
        if any(v is None for v in sub_scores.values()):
            raise ValueError(f"Missing sub-score(s) in LLM response: {result}")

        weights = {
            "required_skills_pct": 0.50,
            "experience_years_pct": 0.20,
            "domain_fit_pct": 0.15,
            "seniority_fit_pct": 0.15,
        }
        weighted = sum(sub_scores[k] * weights[k] for k in weights)
        result["score"] = round(weighted / 100, 3)
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

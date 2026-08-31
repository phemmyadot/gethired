"""
FastAPI routes: resumes, jobs, matches, applications, pipeline trigger.
"""
import logging
import os
import shutil
from uuid import UUID
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..db.models import get_session, Base, get_engine, Resume, Job, JobMatch, AppliedJob, IngestionLog
from ..matching.resume_parser import extract_resume_text, clean_text
from ..ingestion.pipeline import run_ingestion
from ..matching.engine import process_jobs_for_matching, SCORE_THRESHOLD
from ..matching.profile import extract_profile
from ..applying.applicator import run_applications, generate_cover_letter

logger = logging.getLogger(__name__)

app = FastAPI(title="JobBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.getenv("RESUME_UPLOAD_DIR", "/tmp/jobbot_resumes")
AUTO_APPLY_ENABLED = os.getenv("AUTO_APPLY_ENABLED", "false").lower() == "true"
os.makedirs(UPLOAD_DIR, exist_ok=True)

USER_ID = "00000000-0000-0000-0000-000000000001"  # single-user for MVP


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# Resume endpoints
# ─────────────────────────────────────────────

@app.post("/resumes")
async def upload_resume(
    file: UploadFile = File(...),
    label: str = Form(...),
    db: Session = Depends(get_db),
):
    """Upload a resume (PDF or DOCX). Extract text. Save to DB."""
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt"):
        raise HTTPException(400, "Unsupported file type")

    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    content = clean_text(extract_resume_text(save_path))
    if len(content) < 50:
        raise HTTPException(422, "Could not extract text from resume")

    resume = Resume(
        user_id=USER_ID,
        filename=file.filename,
        label=label,
        content=content,
        file_path=save_path,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return {"id": str(resume.id), "label": resume.label, "filename": resume.filename}


@app.get("/resumes")
def list_resumes(db: Session = Depends(get_db)):
    resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
    return [{"id": str(r.id), "label": r.label, "filename": r.filename,
             "created_at": r.created_at, "search_keywords": r.search_keywords,
             "required_keywords": r.required_keywords or []} for r in resumes]


@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: UUID, db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(id=resume_id).first()
    if not r:
        raise HTTPException(404, "Resume not found")
    r.active = False
    db.commit()
    return {"deleted": True}


# ─────────────────────────────────────────────
# Jobs endpoints
# ─────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(
    limit: int = 48,
    offset: int = 0,
    source: str = None,
    sort: str = "fetched",  # "fetched" | "score"
    db: Session = Depends(get_db),
):
    from sqlalchemy import func, nullslast

    best_score_subq = (
        db.query(JobMatch.job_id, func.max(JobMatch.score).label("best_score"))
        .group_by(JobMatch.job_id)
        .subquery()
    )

    q = (
        db.query(Job, best_score_subq.c.best_score)
        .outerjoin(best_score_subq, Job.id == best_score_subq.c.job_id)
        .filter(Job.expired == False)
    )
    if source:
        q = q.filter(Job.source == source)
    total = q.count()

    if sort == "score":
        # Unmatched jobs (NULL score) sort last, not first
        q = q.order_by(nullslast(desc(best_score_subq.c.best_score)), desc(Job.fetched_at))
    else:
        q = q.order_by(desc(Job.fetched_at))

    rows = q.limit(limit).offset(offset).all()
    results = []
    for j, _ in rows:
        applied = db.query(AppliedJob).filter_by(job_id=j.id).first()
        best_match = (
            db.query(JobMatch)
            .filter_by(job_id=j.id)
            .order_by(desc(JobMatch.score))
            .first()
        )
        results.append({
            "id": str(j.id), "title": j.title, "company": j.company,
            "source": j.source, "location": j.location, "remote": j.remote,
            "work_mode": j.work_mode,
            "apply_url": j.apply_url, "fetched_at": j.fetched_at, "posted_at": j.posted_at,
            "applied": applied is not None,
            "application_id": str(applied.id) if applied else None,
            "score": round(best_match.score, 3) if best_match else None,
            "resume_label": best_match.resume.label if best_match and best_match.resume else None,
        })
    return {"items": results, "total": total}


@app.post("/jobs/match-all")
def match_all_jobs(
    background_tasks: BackgroundTasks,
    source: str = None,
    only_unmatched: bool = True,
    db: Session = Depends(get_db),
):
    """
    Score jobs against the primary active resume.
    By default only scores jobs with no existing match; pass only_unmatched=false
    to force a full re-score (e.g. after updating your resume).
    """
    resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
    if not resumes:
        raise HTTPException(400, "No active resumes to match against")

    log = IngestionLog(status="matching", source=source or "all")
    db.add(log)
    db.commit()
    log_id = log.id

    background_tasks.add_task(_run_match_all, log_id, source, only_unmatched)
    return {"message": "Matching started in background", "log_id": str(log_id)}


def _run_match_all(log_id, source: str = None, only_unmatched: bool = True):
    db = get_session()
    try:
        log = db.query(IngestionLog).filter_by(id=log_id).first()
        resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
        if not resumes:
            log.status = "failed"
            log.error = "No active resumes to match against"
            db.commit()
            return

        # Score against the primary (most recently uploaded) resume only —
        # scoring every job against every resume was the main cost driver.
        primary_resume = max(resumes, key=lambda r: r.created_at)
        resumes = [primary_resume]

        q = db.query(Job).filter_by(expired=False)
        if source:
            q = q.filter_by(source=source)
        if only_unmatched:
            matched_job_ids = db.query(JobMatch.job_id).distinct()
            q = q.filter(~Job.id.in_(matched_job_ids))
        jobs = q.all()

        log.jobs_found = len(jobs)
        db.commit()

        matched = 0
        for job in jobs:
            try:
                process_jobs_for_matching([job], resumes, db)
                matched += 1
                log.matches_found = matched
                db.commit()
            except Exception as e:
                logger.error(f"Match failed for job {job.id}: {e}")

        log.status = "done"
        db.commit()
    except Exception as e:
        log.status = "failed"
        log.error = str(e)
        db.commit()
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────
# Matches endpoints
# ─────────────────────────────────────────────

@app.get("/matches")
def list_matches(
    min_score: float = 0.0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """All job matches above a score threshold, with application status."""
    matches = (
        db.query(JobMatch)
        .filter(JobMatch.score >= min_score)
        .order_by(desc(JobMatch.score))
        .limit(limit)
        .all()
    )
    results = []
    for m in matches:
        applied = db.query(AppliedJob).filter_by(job_id=m.job_id).first()
        results.append({
            "job_id":        str(m.job_id),
            "resume_id":     str(m.resume_id),
            "resume_label":  m.resume.label if m.resume else "",
            "job_title":     m.job.title if m.job else "",
            "company":       m.job.company if m.job else "",
            "apply_url":     m.job.apply_url if m.job else "",
            "source":        m.job.source if m.job else "",
            "location":      m.job.location if m.job else None,
            "remote":        m.job.remote if m.job else False,
            "work_mode":     m.job.work_mode if m.job else None,
            "posted_at":     m.job.posted_at if m.job else None,
            "fetched_at":    m.job.fetched_at if m.job else None,
            "score":         round(m.score, 3),
            "reasoning":     m.reasoning,
            "missing_skills": m.missing_skills,
            "selling_points": m.selling_points,
            "applied":       applied is not None,
            "apply_status":  applied.status if applied else None,
            "application_id": str(applied.id) if applied else None,
            "reviewed_at":   m.reviewed_at,
        })
    return results


@app.post("/matches/{job_id}/{resume_id}/apply")
def apply_to_match(job_id: UUID, resume_id: UUID, db: Session = Depends(get_db)):
    """Manually apply to a single matched job."""
    match = db.query(JobMatch).filter_by(job_id=job_id, resume_id=resume_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    if db.query(AppliedJob).filter_by(job_id=job_id).first():
        raise HTTPException(409, "Already applied to this job")

    candidate = {
        "job": match.job,
        "best_resume": match.resume,
        "best_score": match.score,
        "selling_points": match.selling_points or [],
    }
    run_applications([candidate], db)
    return {"message": "Application submitted"}


@app.post("/matches/{job_id}/{resume_id}/cover-letter")
def generate_cover_letter_for_match(job_id: UUID, resume_id: UUID, db: Session = Depends(get_db)):
    """Generate a cover letter for manual apply — does not submit or record anything."""
    match = db.query(JobMatch).filter_by(job_id=job_id, resume_id=resume_id).first()
    if not match:
        raise HTTPException(404, "Match not found")

    cover_letter = generate_cover_letter(match.resume, match.job, match.selling_points or [])
    return {"cover_letter": cover_letter, "apply_url": match.job.apply_url}


@app.post("/matches/{job_id}/{resume_id}/mark-applied")
def mark_match_applied(job_id: UUID, resume_id: UUID, cover_letter: str = "", db: Session = Depends(get_db)):
    """Record that the user manually applied outside the app — no submission attempt."""
    match = db.query(JobMatch).filter_by(job_id=job_id, resume_id=resume_id).first()
    if not match:
        raise HTTPException(404, "Match not found")
    if db.query(AppliedJob).filter_by(job_id=job_id).first():
        raise HTTPException(409, "Already applied to this job")

    record = AppliedJob(
        job_id=job_id,
        resume_id=resume_id,
        match_score=match.score,
        cover_letter=cover_letter,
        status="applied",
    )
    db.add(record)
    db.commit()
    return {"message": "Marked as applied"}


# ─────────────────────────────────────────────
# Applications endpoints
# ─────────────────────────────────────────────

@app.get("/applications")
def list_applications(db: Session = Depends(get_db)):
    apps = db.query(AppliedJob).order_by(desc(AppliedJob.applied_at)).all()
    return [
        {
            "id":           str(a.id),
            "job_title":    a.job.title if a.job else "",
            "company":      a.job.company if a.job else "",
            "resume_label": a.resume.label if a.resume else "",
            "match_score":  a.match_score,
            "status":       a.status,
            "applied_at":   a.applied_at,
            "cover_letter": a.cover_letter,
        }
        for a in apps
    ]


@app.patch("/applications/{app_id}/status")
def update_status(app_id: UUID, status: str, notes: str = None, db: Session = Depends(get_db)):
    """Manually update application status (interview, rejected, offer, etc.)"""
    valid = {"applied", "interview", "rejected", "offer", "withdrawn", "ghosted"}
    if status not in valid:
        raise HTTPException(400, f"Status must be one of: {valid}")
    a = db.query(AppliedJob).filter_by(id=app_id).first()
    if not a:
        raise HTTPException(404)
    a.status = status
    if notes:
        a.notes = notes
    db.commit()
    return {"updated": True}


# ─────────────────────────────────────────────
# Pipeline trigger
# ─────────────────────────────────────────────

@app.post("/pipeline/run")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Manually trigger a full ingest → match → apply cycle."""
    background_tasks.add_task(_run_full_pipeline)
    return {"message": "Pipeline started in background"}


def _serialize_log(log: IngestionLog) -> dict:
    return {
        "id":            str(log.id),
        "status":        log.status,
        "jobs_found":    log.jobs_found,
        "jobs_new":      log.jobs_new,
        "jobs_duped":    log.jobs_duped,
        "matches_found": log.matches_found,
        "error":         log.error,
        "ran_at":        log.ran_at,
    }


@app.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Latest pipeline run's stage and counts, for progress display."""
    log = db.query(IngestionLog).order_by(desc(IngestionLog.ran_at)).first()
    if not log:
        return None
    return _serialize_log(log)


@app.get("/pipeline/status/{log_id}")
def pipeline_status_by_id(log_id: UUID, db: Session = Depends(get_db)):
    """
    Status of one specific run, identified by the log_id returned when it was
    triggered. Use this to track a run you started without it being clobbered
    by unrelated concurrent runs (e.g. the scheduler's periodic ingestion).
    """
    log = db.query(IngestionLog).filter_by(id=log_id).first()
    if not log:
        raise HTTPException(404, "Run not found")
    return _serialize_log(log)


def _run_full_pipeline():
    """Full pipeline: ingest → match → apply."""
    db = get_session()
    log = IngestionLog(status="running")
    db.add(log)
    db.commit()
    try:
        resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
        if not resumes:
            log.status = "done"
            db.commit()
            return

        latest_resume = max(resumes, key=lambda r: r.created_at)
        profile = extract_profile(latest_resume.content)

        if profile is None:
            # Extraction failed — reuse this resume's last successfully saved
            # profile rather than falling back to empty required_keywords,
            # which would disable pre_filter and let every job through.
            logger.warning(
                f"Profile extraction failed for resume {latest_resume.id}; "
                f"reusing previously saved search profile."
            )
            profile = {
                "search_keywords": latest_resume.search_keywords or "software engineer",
                "required_keywords": latest_resume.required_keywords or [],
            }
        else:
            latest_resume.search_keywords = profile["search_keywords"]
            latest_resume.required_keywords = profile["required_keywords"]
            db.commit()

        prefs = {
            "keywords": profile["search_keywords"],
            "required_keywords": profile["required_keywords"],
        }

        log.status = "ingesting"
        db.commit()
        new_jobs = run_ingestion(db, prefs=prefs, log=log)
        if not new_jobs:
            log.status = "done"
            db.commit()
            return

        log.status = "matching"
        db.commit()
        candidates = process_jobs_for_matching(new_jobs, resumes, db)
        log.matches_found = len(candidates)
        db.commit()

        if candidates and AUTO_APPLY_ENABLED:
            log.status = "applying"
            db.commit()
            run_applications(candidates, db)

        log.status = "done"
        db.commit()
    except Exception as e:
        log.status = "failed"
        log.error = str(e)
        db.commit()
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────
# Stats / dashboard summary
# ─────────────────────────────────────────────

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    return {
        "total_jobs":       db.query(Job).count(),
        "total_resumes":    db.query(Resume).filter_by(active=True).count(),
        "total_matches":    db.query(JobMatch).filter(JobMatch.score >= SCORE_THRESHOLD).count(),
        "total_applied":    db.query(AppliedJob).filter_by(status="applied").count(),
        "interviews":       db.query(AppliedJob).filter_by(status="interview").count(),
        "offers":           db.query(AppliedJob).filter_by(status="offer").count(),
        "last_run":         db.query(IngestionLog).order_by(desc(IngestionLog.ran_at)).first(),
        "score_threshold":  SCORE_THRESHOLD,
    }


# ─────────────────────────────────────────────
# Startup: create tables
# ─────────────────────────────────────────────

@app.on_event("startup")
def startup():
    Base.metadata.create_all(get_engine())

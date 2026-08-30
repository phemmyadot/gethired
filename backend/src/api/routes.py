"""
FastAPI routes: resumes, jobs, matches, applications, pipeline trigger.
"""
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
from ..matching.engine import process_jobs_for_matching
from ..applying.applicator import run_applications

app = FastAPI(title="JobBot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.getenv("RESUME_UPLOAD_DIR", "/tmp/jobbot_resumes")
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
             "created_at": r.created_at} for r in resumes]


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
    limit: int = 50,
    offset: int = 0,
    source: str = None,
    db: Session = Depends(get_db),
):
    q = db.query(Job).filter_by(expired=False)
    if source:
        q = q.filter_by(source=source)
    jobs = q.order_by(desc(Job.fetched_at)).limit(limit).offset(offset).all()
    return [
        {
            "id": str(j.id), "title": j.title, "company": j.company,
            "source": j.source, "location": j.location, "remote": j.remote,
            "apply_url": j.apply_url, "fetched_at": j.fetched_at,
        }
        for j in jobs
    ]


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
            "score":         round(m.score, 3),
            "reasoning":     m.reasoning,
            "missing_skills": m.missing_skills,
            "selling_points": m.selling_points,
            "applied":       applied is not None,
            "apply_status":  applied.status if applied else None,
            "reviewed_at":   m.reviewed_at,
        })
    return results


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


def _run_full_pipeline():
    """Full pipeline: ingest → match → apply."""
    db = get_session()
    try:
        resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
        if not resumes:
            return

        new_jobs = run_ingestion(db)
        if not new_jobs:
            return

        candidates = process_jobs_for_matching(new_jobs, resumes, db)
        if candidates:
            run_applications(candidates, db)
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
        "total_matches":    db.query(JobMatch).filter(JobMatch.score >= 0.7).count(),
        "total_applied":    db.query(AppliedJob).filter_by(status="applied").count(),
        "interviews":       db.query(AppliedJob).filter_by(status="interview").count(),
        "offers":           db.query(AppliedJob).filter_by(status="offer").count(),
        "last_run":         db.query(IngestionLog).order_by(desc(IngestionLog.ran_at)).first(),
    }


# ─────────────────────────────────────────────
# Startup: create tables
# ─────────────────────────────────────────────

@app.on_event("startup")
def startup():
    Base.metadata.create_all(get_engine())

"""
Shared match-all orchestration: runs matching as an independently-tracked,
stoppable, resumable background job — decoupled from ingestion so an LLM/
matching failure can never mark a successful ingestion run as failed, and
vice versa. Used by both the API (manual trigger, auto-trigger after
/pipeline/run) and the standalone scheduler process.
"""
import concurrent.futures
import logging
import os
import threading

from ..db.models import get_session, Job, Resume, JobMatch, IngestionLog
from .engine import process_jobs_for_matching

logger = logging.getLogger(__name__)

USER_ID = "00000000-0000-0000-0000-000000000001"  # single-user for MVP

MATCH_ALL_CONCURRENCY = int(os.getenv("MATCH_ALL_CONCURRENCY", "4"))


def _match_one_job(log_id, job_id, resume_id):
    """
    Score a single job against one resume in its own DB session — run inside
    a thread pool, so each worker needs an independent session (SQLAlchemy
    sessions are not thread-safe to share).
    """
    db = get_session()
    try:
        job = db.query(Job).filter_by(id=job_id).first()
        resume = db.query(Resume).filter_by(id=resume_id).first()
        if not job or not resume:
            return
        process_jobs_for_matching([job], [resume], db)
    except Exception as e:
        logger.error(f"Match failed for job {job_id}: {e}")
    finally:
        db.close()


def _is_stopping(log_id) -> bool:
    db = get_session()
    try:
        status = db.query(IngestionLog.status).filter_by(id=log_id).scalar()
        return status == "stopping"
    finally:
        db.close()


def run_match_all(log_id, source: str = None, only_unmatched: bool = True, job_ids: list[str] = None):
    """
    Score jobs against the primary active resume, concurrently, tracked via
    the given IngestionLog row. Cooperatively stoppable via that row's status
    flipping to "stopping" (checked periodically, not per-job).
    """
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
        resume_id = primary_resume.id

        if job_ids:
            jobs = db.query(Job).filter(Job.id.in_(job_ids)).all()
        else:
            q = db.query(Job).filter_by(expired=False)
            if source:
                q = q.filter_by(source=source)
            if only_unmatched:
                matched_job_ids = db.query(JobMatch.job_id).distinct()
                q = q.filter(~Job.id.in_(matched_job_ids))
            jobs = q.all()

        job_ids_to_run = [j.id for j in jobs]
        log.jobs_found = len(job_ids_to_run)
        db.commit()
        db.close()  # this session is done — workers each open their own

        completed = 0
        stopped = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=MATCH_ALL_CONCURRENCY) as executor:
            futures = {
                executor.submit(_match_one_job, log_id, jid, resume_id): jid
                for jid in job_ids_to_run
            }
            for future in concurrent.futures.as_completed(futures):
                future.result()  # surface any unexpected exception
                completed += 1

                # Cooperative cancellation: check every few completions
                # (not every single one) whether the run was asked to stop.
                if completed % MATCH_ALL_CONCURRENCY == 0 and _is_stopping(log_id):
                    stopped = True

                progress_db = get_session()
                try:
                    progress_db.query(IngestionLog).filter_by(id=log_id).update({"matches_found": completed})
                    progress_db.commit()
                finally:
                    progress_db.close()

                if stopped:
                    for f in futures:
                        f.cancel()
                    break

        final_db = get_session()
        try:
            final_log = final_db.query(IngestionLog).filter_by(id=log_id).first()
            if stopped:
                final_log.status = "stopped"
                logger.info(f"Match run {log_id} stopped by request at {completed}/{len(job_ids_to_run)}")
            else:
                final_log.status = "done"
            final_db.commit()
        finally:
            final_db.close()
    except Exception as e:
        fail_db = get_session()
        try:
            fail_log = fail_db.query(IngestionLog).filter_by(id=log_id).first()
            fail_log.status = "failed"
            fail_log.error = str(e)
            fail_db.commit()
        finally:
            fail_db.close()
        raise


def kick_off_match_all(source: str = None):
    """
    Create the tracking log row and launch run_match_all on its own daemon
    thread, fire-and-forget. The caller (ingestion, either via the API or the
    scheduler) returns immediately regardless of how long matching takes or
    whether it ultimately succeeds — matching failures never affect the
    ingestion run's own status, and an already-supported "Match unmatched"
    trigger means nothing is lost if this run fails partway through.
    """
    db = get_session()
    try:
        log = IngestionLog(status="matching", source=source or "all", run_type="match_all")
        db.add(log)
        db.commit()
        log_id = log.id
    finally:
        db.close()

    threading.Thread(
        target=run_match_all,
        args=(log_id, None, True, None),
        daemon=True,
    ).start()

    return log_id

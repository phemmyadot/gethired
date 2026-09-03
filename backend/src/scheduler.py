"""
APScheduler: automatically runs ingestion on a schedule.
Run this alongside the FastAPI server.
"""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from .db.models import get_session, Resume, IngestionLog
from .ingestion.pipeline import run_ingestion
from .matching.profile import extract_profile
from .matching.orchestration import kick_off_match_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_ID = "00000000-0000-0000-0000-000000000001"


def ingest(sources: list[str]):
    """
    One ingestion cycle for a specific set of sources. Matching is
    intentionally NOT run inline here — see matching/orchestration.py for
    why: an LLM/matching failure must never be able to mark a successful
    ingestion run as failed, and vice versa. Matching is kicked off as its
    own independently-tracked background run once ingestion completes.
    """
    db: Session = get_session()
    log = IngestionLog(status="running", source=",".join(sources))
    db.add(log)
    db.commit()
    try:
        resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
        if not resumes:
            logger.warning("No active resumes — skipping ingestion")
            log.status = "done"
            db.commit()
            return

        # Derive search keywords + required_keywords from the primary resume
        # so pre_filter can actually reject irrelevant postings. Without this,
        # required_keywords defaults to empty, which disables filtering
        # entirely — every job from every source passes through unfiltered.
        latest_resume = max(resumes, key=lambda r: r.created_at)
        profile = extract_profile(latest_resume.content)

        if profile is None:
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
            "resume_title": latest_resume.label,
            "resume_job_titles": latest_resume.job_titles or [],
            "required_keywords": profile["required_keywords"],
        }

        logger.info(f"Ingestion start: sources={sources}, keywords={prefs['keywords']!r}")
        db.refresh(log)
        if log.status != "stopping":
            log.status = "ingesting"
            db.commit()
        new_jobs = run_ingestion(db, prefs=prefs, sources=sources, log=log)
        db.refresh(log)
        if log.status != "stopped":
            log.status = "done"
            db.commit()

        if not new_jobs:
            logger.info("No new jobs this cycle")
            return

        logger.info(f"Ingestion complete: {len(new_jobs)} new jobs — kicking off matching")
        kick_off_match_all()
    except Exception as e:
        log.status = "failed"
        log.error = str(e)
        db.commit()
        logger.error(f"Ingestion error: {e}", exc_info=True)
    finally:
        db.close()


def run_scheduler():
    scheduler = BlockingScheduler()

    # Every 1 hour: fast-moving remote/API sources
    scheduler.add_job(
        lambda: ingest(["remotive", "adzuna"]),
        trigger=IntervalTrigger(hours=1),
        id="fast_sources",
        name="Remotive + Adzuna (hourly)",
        max_instances=1,
        coalesce=True,
    )

    # Every 2 hours: ATS sources (Greenhouse + Lever)
    scheduler.add_job(
        lambda: ingest(["greenhouse", "lever"]),
        trigger=IntervalTrigger(hours=2),
        id="ats_sources",
        name="Greenhouse + Lever (every 2h)",
        max_instances=1,
        coalesce=True,
    )

    # Daily at 6am: full re-sync to catch expirations
    scheduler.add_job(
        lambda: ingest(["adzuna", "remotive", "greenhouse", "lever"]),
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_full_sync",
        name="Full daily sync",
        max_instances=1,
    )

    logger.info("Scheduler started — press Ctrl+C to stop")
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()

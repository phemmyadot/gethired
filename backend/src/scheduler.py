"""
APScheduler: automatically runs the pipeline on a schedule.
Run this alongside the FastAPI server.
"""
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from .db.models import get_session, Resume
from .ingestion.pipeline import run_ingestion
from .matching.engine import process_jobs_for_matching
from .applying.applicator import run_applications

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USER_ID = "00000000-0000-0000-0000-000000000001"


def ingest_and_apply(sources: list[str]):
    """One pipeline cycle for a specific set of sources."""
    db: Session = get_session()
    try:
        resumes = db.query(Resume).filter_by(user_id=USER_ID, active=True).all()
        if not resumes:
            logger.warning("No active resumes — skipping pipeline")
            return

        logger.info(f"Pipeline start: sources={sources}, resumes={len(resumes)}")
        new_jobs = run_ingestion(db, sources=sources)

        if not new_jobs:
            logger.info("No new jobs this cycle")
            return

        candidates = process_jobs_for_matching(new_jobs, resumes, db)
        if candidates:
            run_applications(candidates, db)

        logger.info(f"Pipeline complete: {len(new_jobs)} new jobs, {len(candidates)} applied")
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
    finally:
        db.close()


def run_scheduler():
    scheduler = BlockingScheduler()

    # Every 1 hour: fast-moving remote/API sources
    scheduler.add_job(
        lambda: ingest_and_apply(["remotive", "adzuna"]),
        trigger=IntervalTrigger(hours=1),
        id="fast_sources",
        name="Remotive + Adzuna (hourly)",
        max_instances=1,
        coalesce=True,
    )

    # Every 2 hours: ATS sources (Greenhouse + Lever)
    scheduler.add_job(
        lambda: ingest_and_apply(["greenhouse", "lever"]),
        trigger=IntervalTrigger(hours=2),
        id="ats_sources",
        name="Greenhouse + Lever (every 2h)",
        max_instances=1,
        coalesce=True,
    )

    # Daily at 6am: full re-sync to catch expirations
    scheduler.add_job(
        lambda: ingest_and_apply(["adzuna", "remotive", "greenhouse", "lever"]),
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_full_sync",
        name="Full daily sync",
        max_instances=1,
    )

    logger.info("Scheduler started — press Ctrl+C to stop")
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=7, minute=0),
        kwargs={"send_mail": True},
        id="daily_job_digest",
        name="Daily 7AM IST job fetch + email",
    )
    log.info("Scheduler started. Daily run at 07:00 AM IST.")
    log.info("Sources: 20+ (APIs + scrapers) | Email: on | Dedup: on")
    log.info("Press Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    main()

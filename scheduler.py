"""
scheduler.py — long-running process that triggers a fetch cycle every hour.

Run this as its own process alongside the Streamlit app, e.g. via systemd,
supervisor, or a Docker Compose service. See README.md for deployment options.

    python scheduler.py
"""
import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler

from fetcher import run_fetch_cycle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")

FETCH_INTERVAL_MINUTES = 60


def job():
    log.info("Starting scheduled fetch cycle...")
    try:
        run_fetch_cycle()
    except Exception:
        log.exception("Fetch cycle raised an unexpected error")


if __name__ == "__main__":
    # Run once immediately on startup so the dashboard isn't empty while waiting
    # for the first hourly tick.
    job()

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(job, "interval", minutes=FETCH_INTERVAL_MINUTES, next_run_time=None)
    log.info("Scheduler started — fetching every %d minutes.", FETCH_INTERVAL_MINUTES)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")

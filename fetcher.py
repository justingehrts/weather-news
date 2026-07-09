"""
fetcher.py — pulls all enabled RSS feeds, keeps items from the last N days,
dedupes by link, and writes new articles into the SQLite cache.

Run standalone for a one-off fetch:
    python fetcher.py

Or import run_fetch_cycle() from the scheduler / Streamlit "refresh now" button.
"""
import time
import logging
from datetime import datetime, timezone
import feedparser

import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fetcher")

# How far back to keep articles when pulling feeds (matches the dashboard's default window)
LOOKBACK_DAYS = 2
REQUEST_TIMEOUT = 15  # seconds, per feed


def _entry_timestamp(entry) -> float:
    """Best-effort published/updated time as a unix timestamp. Falls back to now."""
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None)
        if val:
            return time.mktime(val)
    return time.time()


def fetch_one_feed(source: dict) -> tuple[int, int, str | None]:
    """
    Fetch a single feed. Returns (new_articles_count, total_entries_seen, error_message).
    error_message is None on success.
    """
    name, url = source["name"], source["feed_url"]
    try:
        parsed = feedparser.parse(url, request_headers={"User-Agent": "weather-dashboard/1.0"})
    except Exception as e:  # feedparser rarely raises, but be defensive
        return 0, 0, f"{type(e).__name__}: {e}"

    if parsed.bozo and not parsed.entries:
        # bozo=True just means "not strictly well-formed XML"; only treat as
        # a hard failure if we got zero usable entries out of it.
        return 0, 0, f"parse error: {getattr(parsed, 'bozo_exception', 'unknown')}"

    cutoff = time.time() - LOOKBACK_DAYS * 86400
    new_count = 0
    for entry in parsed.entries:
        published_ts = _entry_timestamp(entry)
        if published_ts < cutoff:
            continue
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        if not title or not link:
            continue
        # Keep summaries short — this is a headline dashboard, not a reader.
        summary = summary[:300]
        if db.upsert_article(name, title, link, summary, published_ts):
            new_count += 1

    return new_count, len(parsed.entries), None


def run_fetch_cycle():
    db.init_db()
    db.sync_sources_from_code()

    sources = db.list_sources(enabled_only=True)
    ok, failed, total_new = 0, 0, 0
    details = []

    for source in sources:
        new_count, seen, err = fetch_one_feed(source)
        if err:
            failed += 1
            details.append(f"FAILED  {source['name']}: {err}")
            log.warning("Feed failed: %s (%s) — %s", source["name"], source["feed_url"], err)
        else:
            ok += 1
            total_new += new_count
            details.append(f"ok      {source['name']}: {new_count} new / {seen} seen")
            log.info("Fetched %s: %d new / %d seen", source["name"], new_count, seen)

    db.prune_old_articles(days=14)
    db.log_fetch_run(ok, failed, total_new, "\n".join(details))
    log.info("Fetch cycle complete: %d ok, %d failed, %d new articles", ok, failed, total_new)
    return ok, failed, total_new


if __name__ == "__main__":
    run_fetch_cycle()

"""
db.py — SQLite storage layer for the weather dashboard.

Two tables:
  sources  — the list of RSS feeds to poll (editable from the UI)
  articles — the deduped article cache the dashboard reads from
"""
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "weather_dashboard.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # lets the scheduler write while Streamlit reads
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT 'general',
                enabled INTEGER DEFAULT 1,
                added_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL UNIQUE,
                summary TEXT,
                published_ts REAL,
                fetched_ts REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at REAL DEFAULT (strftime('%s','now')),
                sources_ok INTEGER,
                sources_failed INTEGER,
                new_articles INTEGER,
                details TEXT
            )
        """)


SEED_SOURCES = [
    # Official government sources — these are stable, high-confidence feeds.
    ("NOAA (all news)", "https://www.noaa.gov/rss.xml", "official"),
    ("National Hurricane Center - Atlantic", "https://www.nhc.noaa.gov/index-at.xml", "official"),
    ("National Hurricane Center - E. Pacific", "https://www.nhc.noaa.gov/index-ep.xml", "official"),
    ("Storm Prediction Center - Outlooks", "https://www.spc.noaa.gov/products/spcrss.xml", "official"),

    # Fox Weather — confirmed official RSS program (moxie.foxweather.com).
    ("Fox Weather - Latest Headlines", "https://moxie.foxweather.com/google-publisher/latest.xml", "major"),
    ("Fox Weather - Extreme Weather", "https://moxie.foxweather.com/google-publisher/extreme-weather.xml", "major"),

    # Independent weather blogs / newsletter-style sources.
    # Verify these once deployed — smaller sites change feed paths more often.
    ("Tropical Tidbits (Levi Cowan)", "https://www.tropicaltidbits.com/blog/feed", "blog"),
    ("Watts Up With That", "https://wattsupwiththat.com/feed/", "blog"),
]


def sync_sources_from_code():
    """
    Makes the `sources` table exactly match SEED_SOURCES on every startup.
    This is what lets editing db.py + redeploying actually take effect, even
    on a persistent host where the database isn't wiped between deploys —
    add/remove a tuple in SEED_SOURCES and it's reflected here automatically.
    """
    with get_conn() as conn:
        for name, url, category in SEED_SOURCES:
            existing = conn.execute("SELECT id FROM sources WHERE feed_url = ?", (url,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE sources SET name = ?, category = ? WHERE feed_url = ?",
                    (name, category, url),
                )
            else:
                conn.execute(
                    "INSERT INTO sources (name, feed_url, category) VALUES (?, ?, ?)",
                    (name, url, category),
                )
        seed_urls = {url for _, url, _ in SEED_SOURCES}
        rows = conn.execute("SELECT id, feed_url FROM sources").fetchall()
        for row in rows:
            if row["feed_url"] not in seed_urls:
                conn.execute("DELETE FROM sources WHERE id = ?", (row["id"],))


def list_sources(enabled_only=False):
    with get_conn() as conn:
        q = "SELECT * FROM sources"
        if enabled_only:
            q += " WHERE enabled = 1"
        q += " ORDER BY category, name"
        return [dict(r) for r in conn.execute(q).fetchall()]


def upsert_article(source_name, title, link, summary, published_ts):
    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM articles WHERE link = ?", (link,))
        if cur.fetchone():
            return False  # already have it
        conn.execute(
            "INSERT INTO articles (source_name, title, link, summary, published_ts) VALUES (?, ?, ?, ?, ?)",
            (source_name, title, link, summary, published_ts),
        )
        return True


def get_recent_articles(hours=48):
    cutoff = time.time() - hours * 3600
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM articles WHERE published_ts >= ? ORDER BY published_ts DESC",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def prune_old_articles(days=14):
    cutoff = time.time() - days * 86400
    with get_conn() as conn:
        conn.execute("DELETE FROM articles WHERE published_ts < ?", (cutoff,))


def log_fetch_run(sources_ok, sources_failed, new_articles, details=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO fetch_log (sources_ok, sources_failed, new_articles, details) VALUES (?, ?, ?, ?)",
            (sources_ok, sources_failed, new_articles, details),
        )


def get_last_fetch_run():
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM fetch_log ORDER BY ran_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

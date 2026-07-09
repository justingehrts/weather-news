"""
app.py — Streamlit weather headlines dashboard.

Reads articles from the SQLite cache (populated by fetcher.py / scheduler.py)
and displays them as cards with source, timestamp, snippet, and a link out.
Includes a sidebar to manage sources (add/enable/disable/remove) and a
manual "fetch now" button as a backstop to the hourly scheduler.
"""
import time
from datetime import datetime, timezone

import streamlit as st

import db
from fetcher import run_fetch_cycle

st.set_page_config(page_title="Weather Headlines", page_icon="⛈️", layout="wide")

db.init_db()
db.sync_sources_from_code()

# Auto-refresh on page load if the cache is stale. This makes the app
# self-sufficient on platforms like Streamlit Community Cloud, which only
# runs `streamlit run app.py` and can't also run scheduler.py as a second
# process. If you're deploying via Docker Compose with scheduler.py running
# alongside, this just becomes a no-op safety net most of the time since the
# cache will rarely be stale.
STALE_AFTER_SECONDS = 3600


def maybe_auto_fetch():
    last_run = db.get_last_fetch_run()
    is_stale = (last_run is None) or (time.time() - last_run["ran_at"] > STALE_AFTER_SECONDS)
    if is_stale:
        with st.spinner("Fetching latest headlines..."):
            run_fetch_cycle()


maybe_auto_fetch()


def fmt_time_ago(ts: float) -> str:
    if not ts:
        return "unknown time"
    delta = datetime.now(timezone.utc).timestamp() - ts
    hours = delta / 3600
    if hours < 1:
        return f"{int(delta / 60)} min ago"
    if hours < 24:
        return f"{hours:.0f} hr ago"
    return f"{hours / 24:.0f} days ago"


# ---------- Sidebar: source list (read-only — edit SEED_SOURCES in db.py to change) ----------
with st.sidebar:
    st.header("Sources")
    st.caption("Managed in `db.py` — edit `SEED_SOURCES` and push to GitHub to add or remove one.")

    sources = db.list_sources()
    if sources:
        by_category: dict[str, list[dict]] = {}
        for s in sources:
            by_category.setdefault(s["category"], []).append(s)
        for category, items in sorted(by_category.items()):
            st.markdown(f"**{category}**")
            for s in items:
                st.caption(f"• {s['name']}")
    else:
        st.caption("No sources configured.")

    st.divider()
    last_run = db.get_last_fetch_run()
    if last_run:
        st.caption(
            f"Last fetch: {fmt_time_ago(last_run['ran_at'])}  \n"
            f"{last_run['sources_ok']} ok / {last_run['sources_failed']} failed, "
            f"{last_run['new_articles']} new articles"
        )
        with st.expander("Fetch details"):
            st.text(last_run["details"])
    else:
        st.caption("No fetch has run yet.")

    if st.button("🔄 Fetch now", use_container_width=True):
        with st.spinner("Fetching feeds..."):
            ok, failed, new = run_fetch_cycle()
        st.success(f"Done: {ok} ok, {failed} failed, {new} new articles")
        st.rerun()


# ---------- Main: headlines ----------
st.title("⛈️ Weather Headlines")

col1, col2 = st.columns([3, 1])
with col1:
    st.caption("Aggregated from official sources, major outlets, and independent weather writers.")
with col2:
    window_hours = st.selectbox("Show last", options=[24, 48, 72], index=1, format_func=lambda h: f"{h} hours")

articles = db.get_recent_articles(hours=window_hours)

if not articles:
    st.info(
        "No articles yet. Click **Fetch now** in the sidebar to pull the first batch, "
        "or wait for the hourly scheduler to run."
    )
else:
    st.caption(f"{len(articles)} headlines in the last {window_hours} hours")

    # Group by source for a cleaner "at a glance by outlet" scan, most-recent first within each.
    by_source: dict[str, list[dict]] = {}
    for a in articles:
        by_source.setdefault(a["source_name"], []).append(a)

    for source_name, items in sorted(by_source.items(), key=lambda kv: -max(i["published_ts"] for i in kv[1])):
        st.subheader(source_name)
        for a in items:
            with st.container(border=True):
                st.markdown(f"#### [{a['title']}]({a['link']})")
                st.caption(fmt_time_ago(a["published_ts"]))
                if a["summary"]:
                    st.write(a["summary"])

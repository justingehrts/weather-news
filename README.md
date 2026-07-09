# Weather Headlines Dashboard

A Streamlit dashboard that aggregates weather headlines from official sources,
major outlets, and independent weather writers/Substacks — pulled via RSS,
refreshed hourly, showing only the last 1-2 days.

## How it works

- **`db.py`** — SQLite storage, plus the `SEED_SOURCES` list, which is the single source of truth for which feeds get pulled
- **`fetcher.py`** — pulls every source in `SEED_SOURCES`, keeps items from the last 2 days, dedupes by link
- **`scheduler.py`** — a small standalone process that runs the fetcher every hour (optional — see deployment notes below)
- **`app.py`** — the Streamlit dashboard itself, reads from the same SQLite file, and auto-fetches on load if the cache is stale

Sources are hardcoded in `db.py`, not editable from the UI. On every startup,
`db.sync_sources_from_code()` makes the database's `sources` table exactly
match `SEED_SOURCES` — so editing that list and redeploying is all it takes
to add, remove, or rename a source, on any deployment path.

## Sources

Configured in `SEED_SOURCES` at the top of `db.py`:

| Source | Type | Confidence |
|---|---|---|
| NOAA (all news) | Official (.gov) | High |
| National Hurricane Center — Atlantic / E. Pacific | Official (.gov) | High |
| Storm Prediction Center — Outlooks | Official (.gov) | High |
| Fox Weather — Latest Headlines / Extreme Weather | Major outlet | High |
| Tropical Tidbits (Levi Cowan) | Independent blog | Verify after deploy |
| Watts Up With That | Independent blog | Verify after deploy |

I couldn't find a currently-working official RSS feed for The Weather Channel
(weather.com) or the Associated Press directly — AP discontinued official RSS
some time ago, and weather.com doesn't appear to publish one. Fox Weather's
feed program is a solid substitute for "major outlet" coverage. To add another
outlet or Substack, add a tuple to `SEED_SOURCES` in `db.py` and push it —
most Substacks work by appending `/feed` to the publication's URL (e.g.
`https://name.substack.com/feed`). To remove one, delete its tuple. To
temporarily disable one without deleting it, comment the line out.

**Note on testing:** I built this without live internet access to verify each
feed URL still resolves (my sandbox can only reach package repos, not arbitrary
sites). The official .gov and Fox Weather feeds are well-established and
should work; give the blog feeds a check after deploying, and use the sidebar's
"Fetch details" panel to see exactly which feeds succeeded or failed on any run.

## Running locally

```bash
pip install -r requirements.txt
python fetcher.py        # do one fetch to populate the DB
streamlit run app.py     # open the dashboard
```

For continuous hourly fetching locally, run `python scheduler.py` in a second terminal.

## Deploying to Streamlit Community Cloud

This is the fastest path if you just want it live with zero server management:

1. Push this folder to a GitHub repo (public or private)
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, click **New app**
3. Point it at your repo, branch, and set the main file path to `app.py`
4. Deploy

The app fetches feeds inline on page load whenever the cache is more than an
hour old (see `maybe_auto_fetch()` in `app.py`), so it self-refreshes without
needing `scheduler.py` running separately — Community Cloud only runs the one
`streamlit run app.py` process, so this was a required adjustment from the
original design.

**Worth knowing about this platform:**
- **Sleeping:** free-tier apps sleep after a period of no visitors and wake on
  the next visit — the wake-up will trigger a fetch if the cache is stale, so
  you might see a few seconds' delay on the first load after it's been idle.
- **Ephemeral storage:** the SQLite file resets whenever the app reboots or
  you push a new commit. This is a non-issue now — the article cache just
  rebuilds itself (harmless, it re-fetches), and since sources live in
  `SEED_SOURCES` in `db.py` rather than the database, they come back exactly
  as configured every time, with nothing to lose.

## Deploying (alternative: Docker Compose on your own server)

This runs the dashboard and the hourly scheduler as two containers sharing one
persistent SQLite volume — works on any VPS/cloud box you control (a small
DigitalOcean droplet, Linode, EC2 instance, etc.).

```bash
docker compose up -d --build
```

Then put a reverse proxy (Caddy, nginx, or Cloudflare Tunnel) in front of port
`8501` to serve it on your domain with HTTPS. Caddy is the least fiddly if you
haven't set one up before — a `Caddyfile` with:

```
weather.yourdomain.com {
    reverse_proxy localhost:8501
}
```

...gets you automatic HTTPS in one line.

## Alternative: no Docker, just cron

If you'd rather not use Docker, you can:
1. Run `streamlit run app.py` under `systemd` or a process manager like `supervisor`/`pm2` so it stays up
2. Add a cron entry instead of `scheduler.py`:
   ```
   0 * * * * cd /path/to/weather-dashboard && /usr/bin/python3 fetcher.py >> fetch.log 2>&1
   ```

Either approach gives you the same hourly refresh — Docker Compose is just the
more portable, one-command option.

## Adding/removing sources

Edit `SEED_SOURCES` in `db.py`:

```python
SEED_SOURCES = [
    ("NOAA (all news)", "https://www.noaa.gov/rss.xml", "official"),
    ...
    ("My New Source", "https://example.com/feed", "custom"),  # add a tuple
]
```

Push the change to GitHub (or restart the app if self-hosting). It takes
effect on the next startup, since `sync_sources_from_code()` re-syncs the
database to match this list every time the app starts — no manual DB editing,
no sidebar, no drift between what's in code and what's actually running.

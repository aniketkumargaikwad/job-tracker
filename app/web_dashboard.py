"""Flask web dashboard — terminal-themed job tracker with full history & logs.

Routes:
  /                   – All jobs table with search/filter/sort
  /history            – Application history
  /stats              – Pipeline statistics + charts
  /runs               – Pipeline run log with details
  /apply/<id>         – Redirect to portal (Quick Apply)
  /mark-applied/<id>  – Mark a job as manually applied
  /api/jobs           – JSON API for jobs
  /api/history        – JSON API for application history
  /api/stats          – JSON API for stats
  /api/trigger-run    – Trigger a pipeline run (async)
"""
from __future__ import annotations

import html as html_mod
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, redirect, request, url_for

from app.config import SETTINGS
from app.db import fetch_all_jobs, fetch_applications, fetch_stats, get_conn, init_db

app = Flask(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _esc(v) -> str:
    return html_mod.escape(str(v)) if v else ""

def _time_ago(iso_str: str) -> str:
    """Convert ISO datetime to human-readable time ago."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return iso_str[:16]


# ── Theme ────────────────────────────────────────────────────────────────────

_CSS = """
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --green: #3fb950; --dim-green: #238636; --text: #c9d1d9;
    --dim: #8b949e; --bright: #f0f6fc; --red: #f85149;
    --orange: #d29922; --blue: #58a6ff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg); color: var(--text); font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  .container { max-width: 1400px; margin: 0 auto; padding: 16px; }
  a { color: var(--blue); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* NAV */
  .nav {
    background: var(--card); border-bottom: 1px solid var(--border);
    padding: 12px 24px; display: flex; align-items: center; gap: 24px;
    position: sticky; top: 0; z-index: 100;
  }
  .nav-brand { color: var(--green); font-weight: 700; font-size: 16px; letter-spacing: 1px; }
  .nav a.nav-link { color: var(--dim); font-size: 13px; font-weight: 500; }
  .nav a.nav-link:hover, .nav a.nav-link.active { color: var(--bright); text-decoration: none; }
  .nav .nav-right { margin-left: auto; color: var(--dim); font-size: 12px; }

  /* CARDS */
  .stat-row { display: flex; gap: 16px; margin: 20px 0; flex-wrap: wrap; }
  .stat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px 20px; min-width: 150px; flex: 1;
  }
  .stat-num { font-size: 28px; font-weight: 700; color: var(--green); }
  .stat-label { font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }

  /* SEARCH */
  .search-bar {
    width: 100%; padding: 10px 14px; background: var(--card); border: 1px solid var(--border);
    border-radius: 6px; color: var(--text); font-size: 14px; margin: 16px 0;
  }
  .search-bar:focus { outline: none; border-color: var(--green); }
  .search-bar::placeholder { color: var(--dim); }

  /* TABLE */
  table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; margin-top: 8px; }
  thead { background: var(--bg); }
  th {
    padding: 10px 12px; text-align: left; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px; color: var(--dim);
    border-bottom: 1px solid var(--border);
  }
  td { padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: top; }
  tr:hover { background: #1c2128; }
  td.title-cell { max-width: 280px; }
  td.skills-cell { font-size: 11px; color: var(--dim); max-width: 200px; }

  /* BADGES */
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 11px; font-weight: 600;
  }
  .badge-green { background: rgba(63,185,80,0.15); color: var(--green); }
  .badge-orange { background: rgba(210,153,34,0.15); color: var(--orange); }
  .badge-red { background: rgba(248,81,73,0.15); color: var(--red); }
  .badge-blue { background: rgba(88,166,255,0.15); color: var(--blue); }
  .badge-dim { background: rgba(139,148,158,0.15); color: var(--dim); }
  .check { color: var(--green); } .cross { color: var(--dim); }

  /* BUTTONS */
  .btn {
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    font-size: 12px; font-weight: 600; text-decoration: none; cursor: pointer; border: none;
  }
  .btn-green { background: var(--dim-green); color: var(--bright); }
  .btn-green:hover { background: var(--green); text-decoration: none; }
  .btn-outline { border: 1px solid var(--border); background: transparent; color: var(--dim); }
  .btn-outline:hover { border-color: var(--dim); color: var(--text); text-decoration: none; }

  /* SCORE BAR */
  .score-bar { display: inline-block; width: 50px; height: 6px; background: var(--border); border-radius: 3px; vertical-align: middle; margin-right: 6px; }
  .score-fill { height: 100%; border-radius: 3px; }

  h1 { font-size: 20px; color: var(--bright); margin: 20px 0 8px; }
  h2 { font-size: 16px; color: var(--bright); margin: 24px 0 12px; }
  .subtitle { color: var(--dim); font-size: 13px; margin-bottom: 12px; }
  .footer { margin-top: 40px; padding: 16px 0; border-top: 1px solid var(--border); color: var(--dim); font-size: 11px; text-align: center; }
  .toast {
    position: fixed; top: 20px; right: 20px; background: var(--dim-green); color: white;
    padding: 12px 20px; border-radius: 8px; font-size: 13px; z-index: 999;
    animation: fadeout 3s forwards; animation-delay: 2s;
  }
  @keyframes fadeout { to { opacity: 0; visibility: hidden; } }
</style>
"""

def _nav(active: str = "") -> str:
    links = [("/", "Jobs", "jobs"), ("/history", "History", "history"),
             ("/stats", "Stats", "stats"), ("/runs", "Run Log", "runs")]
    items = "".join(
        f'<a class="nav-link {"active" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in links
    )
    return f"""<div class="nav">
      <span class="nav-brand">JOB TRACKER</span>{items}
      <span class="nav-right">v3.0 | Daily 07:00 IST</span>
    </div>"""


def _page(title: str, active: str, body: str, toast: str = "") -> str:
    toast_html = f'<div class="toast">{_esc(toast)}</div>' if toast else ""
    return f"""<!DOCTYPE html><html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>{_CSS}</head>
<body>{_nav(active)}<div class="container">{toast_html}{body}</div>
<div class="footer">Remote .NET Job Automation | SQLite + Flask | Zero Cost</div>
</body></html>"""


def _score_badge(score: float) -> str:
    color = "var(--green)" if score >= 60 else "var(--orange)" if score >= 35 else "var(--red)"
    pct = min(score, 100)
    return (f'<span class="score-bar"><span class="score-fill" '
            f'style="width:{pct}%;background:{color};"></span></span>'
            f'<span style="color:{color};font-size:12px;font-weight:600;">{score:.0f}</span>')


def _status_badge(status: str) -> str:
    m = {"applied": "badge-green", "emailed": "badge-orange", "failed": "badge-red", "not_applied": "badge-dim"}
    return f'<span class="badge {m.get(status, "badge-dim")}">{_esc(status)}</span>'


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    init_db()
    query = request.args.get("q", "")
    rows = fetch_all_jobs(query, limit=500)
    s = fetch_stats()

    # Stats bar
    stats_html = f"""<div class="stat-row">
      <div class="stat-card"><div class="stat-num">{s['total_jobs']}</div><div class="stat-label">Total Jobs</div></div>
      <div class="stat-card"><div class="stat-num">{s['emailed']}</div><div class="stat-label">Emailed</div></div>
      <div class="stat-card"><div class="stat-num">{s['applied']}</div><div class="stat-label">Applied</div></div>
      <div class="stat-card"><div class="stat-num">{len(s['sources'])}</div><div class="stat-label">Sources</div></div>
    </div>"""

    # Job rows
    job_rows = ""
    for r in rows:
        mnc = '<span class="check">Yes</span>' if r["is_mnc"] else '<span class="cross">-</span>'
        prod = '<span class="check">Yes</span>' if r["is_product_based"] else '<span class="cross">-</span>'
        cities = _esc(r["indian_cities_csv"]) if r["indian_cities_csv"] else "-"
        job_rows += f"""<tr>
          <td>{r['id']}</td>
          <td class="title-cell"><strong>{_esc(r['title'])}</strong><br><span style="color:var(--dim);font-size:11px;">{_esc(r['source'])}</span></td>
          <td>{_esc(r['company'])}</td>
          <td class="skills-cell">{_esc(r['skills_csv'])}</td>
          <td>{mnc}</td><td>{prod}</td>
          <td style="font-size:11px;">{cities}</td>
          <td style="font-size:12px;">{_esc(r['salary'])}</td>
          <td>{_score_badge(r['relevance_score'])}</td>
          <td>{_status_badge(r['status'])}</td>
          <td>
            <a href="{_esc(r['apply_link'])}" target="_blank" class="btn btn-green" title="Open job portal">Apply &#8599;</a>
            <a href="/mark-applied/{r['id']}" class="btn btn-outline" style="margin-top:4px;display:block;text-align:center;" title="Mark as applied">Done</a>
          </td>
        </tr>"""

    body = f"""
    <h1>Remote .NET Jobs</h1>
    <p class="subtitle">Showing {len(rows)} jobs {f'matching "<strong>{_esc(query)}</strong>"' if query else ''}</p>
    {stats_html}
    <form method="get" action="/">
      <input class="search-bar" name="q" value="{_esc(query)}" placeholder="Search jobs by title, company, or skills...">
    </form>
    <table>
      <thead><tr>
        <th>#</th><th>Title / Source</th><th>Company</th><th>Skills</th><th>MNC</th><th>Prod</th>
        <th>Cities</th><th>Salary</th><th>Score</th><th>Status</th><th>Action</th>
      </tr></thead>
      <tbody>{job_rows}</tbody>
    </table>"""

    return _page("Jobs Dashboard", "jobs", body)


@app.route("/mark-applied/<int:job_id>")
def mark_applied(job_id: int):
    """Mark a job as manually applied."""
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status = 'applied' WHERE id = ?", (job_id,))
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "manual", "applied", "Marked via dashboard", datetime.now(timezone.utc).isoformat()),
        )
    return redirect(url_for("index", _external=False))


@app.route("/apply/<int:job_id>")
def quick_apply(job_id: int):
    """Quick Apply — redirect user to the job portal link."""
    with get_conn() as conn:
        row = conn.execute("SELECT apply_link FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return _page("Not Found", "jobs", "<h1>Job not found</h1>")
    return redirect(row["apply_link"])


@app.route("/history")
def history():
    init_db()
    rows = fetch_applications(limit=500)
    app_rows = ""
    for r in rows:
        app_rows += f"""<tr>
          <td>{r['id']}</td>
          <td>{r['job_id']}</td>
          <td>{_esc(r['title'])}</td>
          <td>{_esc(r['company'])}</td>
          <td><span class="badge badge-blue">{_esc(r['portal'])}</span></td>
          <td>{_status_badge(r['status'])}</td>
          <td style="font-size:11px;">{_esc(r['details'])}</td>
          <td style="font-size:12px;">{_time_ago(r['attempted_at'])}</td>
          <td><a href="{_esc(r['apply_link'])}" target="_blank" class="btn btn-outline">Open &#8599;</a></td>
        </tr>"""

    body = f"""
    <h1>Application History</h1>
    <p class="subtitle">{len(rows)} records</p>
    <table>
      <thead><tr>
        <th>#</th><th>Job</th><th>Title</th><th>Company</th><th>Portal</th>
        <th>Status</th><th>Details</th><th>When</th><th>Link</th>
      </tr></thead>
      <tbody>{app_rows}</tbody>
    </table>"""
    return _page("History", "history", body)


@app.route("/stats")
def stats_page():
    init_db()
    s = fetch_stats()

    source_rows = "".join(
        f'<tr><td>{_esc(name)}</td><td style="font-weight:600;">{cnt}</td>'
        f'<td><div style="background:var(--dim-green);height:8px;border-radius:4px;'
        f'width:{min(cnt * 2, 300)}px;"></div></td></tr>'
        for name, cnt in s["sources"]
    )

    run_rows = ""
    for r in s["recent_runs"]:
        duration = ""
        if r["started_at"] and r["finished_at"]:
            try:
                t0 = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(r["finished_at"].replace("Z", "+00:00"))
                duration = f"{(t1 - t0).total_seconds():.0f}s"
            except Exception:
                duration = "-"
        stats_detail = _esc(r["source_stats"]) if r["source_stats"] else "-"
        run_rows += f"""<tr>
          <td>{r['id']}</td>
          <td style="font-size:12px;">{_time_ago(r['started_at'])}</td>
          <td>{duration or '-'}</td>
          <td style="font-weight:600;">{r['fetched_count']}</td>
          <td style="font-weight:600;color:var(--green);">{r['stored_count']}</td>
          <td style="font-size:11px;">{stats_detail}</td>
        </tr>"""

    body = f"""
    <h1>Pipeline Statistics</h1>
    <div class="stat-row">
      <div class="stat-card"><div class="stat-num">{s['total_jobs']}</div><div class="stat-label">Total Jobs in DB</div></div>
      <div class="stat-card"><div class="stat-num">{s['emailed']}</div><div class="stat-label">Emailed</div></div>
      <div class="stat-card"><div class="stat-num">{s['applied']}</div><div class="stat-label">Applied</div></div>
      <div class="stat-card"><div class="stat-num">{s['failed']}</div><div class="stat-label">Failed</div></div>
    </div>

    <h2>Jobs by Source</h2>
    <table style="max-width:600px;">
      <thead><tr><th>Source</th><th>Count</th><th>Volume</th></tr></thead>
      <tbody>{source_rows}</tbody>
    </table>

    <h2>Pipeline Run History</h2>
    <table>
      <thead><tr><th>Run</th><th>When</th><th>Duration</th><th>Fetched</th><th>Saved</th><th>Details</th></tr></thead>
      <tbody>{run_rows}</tbody>
    </table>"""
    return _page("Stats", "stats", body)


@app.route("/runs")
def runs_page():
    init_db()
    with get_conn() as conn:
        runs = conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 50").fetchall()

    run_rows = ""
    for r in runs:
        started = _time_ago(r["started_at"])
        finished = _time_ago(r["finished_at"]) if r["finished_at"] else '<span class="badge badge-orange">running</span>'
        errors = _esc(r["errors"]) if r["errors"] else "-"
        stats_detail = _esc(r["source_stats"]) if r["source_stats"] else "-"

        duration = "-"
        if r["started_at"] and r["finished_at"]:
            try:
                t0 = datetime.fromisoformat(r["started_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(r["finished_at"].replace("Z", "+00:00"))
                duration = f"{(t1 - t0).total_seconds():.0f}s"
            except Exception:
                pass

        run_rows += f"""<tr>
          <td style="font-weight:600;">#{r['id']}</td>
          <td>{started}</td><td>{finished}</td><td>{duration}</td>
          <td style="font-weight:600;">{r['fetched_count']}</td>
          <td style="font-weight:600;color:var(--green);">{r['stored_count']}</td>
          <td style="font-size:11px;">{stats_detail}</td>
          <td style="font-size:11px;color:var(--red);">{errors}</td>
        </tr>"""

    body = f"""
    <h1>Pipeline Run Log</h1>
    <p class="subtitle">Last 50 runs</p>
    <table>
      <thead><tr>
        <th>Run</th><th>Started</th><th>Finished</th><th>Duration</th>
        <th>Fetched</th><th>Saved</th><th>Stats</th><th>Errors</th>
      </tr></thead>
      <tbody>{run_rows}</tbody>
    </table>"""
    return _page("Run Log", "runs", body)


# ── JSON APIs ────────────────────────────────────────────────────────────────

@app.route("/api/jobs")
def api_jobs():
    init_db()
    query = request.args.get("q", "")
    rows = fetch_all_jobs(query, limit=200)
    return jsonify([dict(r) for r in rows])


@app.route("/api/history")
def api_history():
    init_db()
    rows = fetch_applications(limit=200)
    return jsonify([dict(r) for r in rows])


@app.route("/api/stats")
def api_stats():
    init_db()
    return jsonify(fetch_stats())


@app.route("/api/trigger-run", methods=["POST"])
def api_trigger_run():
    """Trigger a pipeline run in the background. Returns immediately."""
    def _bg_run():
        from app.pipeline import run_pipeline
        run_pipeline(send_mail=True)

    thread = threading.Thread(target=_bg_run, daemon=True)
    thread.start()
    return jsonify({"status": "started", "message": "Pipeline run triggered in background"})


# ── Entry point ──────────────────────────────────────────────────────────────

def run_web_dashboard() -> None:
    init_db()
    host = SETTINGS.dashboard_host
    port = SETTINGS.dashboard_port
    print(f"Dashboard: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)

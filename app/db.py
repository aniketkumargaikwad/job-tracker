from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.models import EnrichedJob

# ── Backend detection ────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_USE_PG = DATABASE_URL.startswith("postgres")

if _USE_PG:
    import psycopg2
    import psycopg2.extras

# Allow override for testing (set to ":memory:" or temp path)
_db_path_override: Optional[str] = None


def set_db_path(path: Optional[str]) -> None:
    """Override the database path (SQLite only). Use None to reset."""
    global _db_path_override, _USE_PG
    _db_path_override = path
    # When overriding path, force SQLite mode (for tests)
    if path is not None:
        _USE_PG = False
    else:
        _USE_PG = DATABASE_URL.startswith("postgres")


# ── Connection helpers ───────────────────────────────────────────────────────

def _pg_conn():
    """Create a PostgreSQL connection with retry for transient failures."""
    import time as _time
    for attempt in range(3):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError:
            if attempt < 2:
                _time.sleep(1 * (attempt + 1))
            else:
                raise


def _sqlite_conn():
    db_path = _db_path_override or ":memory:"
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_conn():
    """Return a raw connection (PG or SQLite)."""
    if _USE_PG:
        return _pg_conn()
    return _sqlite_conn()


@contextmanager
def _cursor():
    """Yield a dict-cursor that works on both backends."""
    if _USE_PG:
        conn = _pg_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
    else:
        conn = _sqlite_conn()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _ph(name: str = "") -> str:
    """Parameter placeholder: %s for PG, ? for SQLite."""
    return "%s" if _USE_PG else "?"


# ── Schema ───────────────────────────────────────────────────────────────────

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    apply_link TEXT NOT NULL,
    skills_csv TEXT NOT NULL,
    is_mnc INTEGER NOT NULL,
    is_product_based INTEGER NOT NULL,
    indian_cities_csv TEXT NOT NULL,
    salary TEXT NOT NULL,
    experience TEXT NOT NULL DEFAULT '',
    relevance_score REAL NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'not_applied',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

CREATE TABLE IF NOT EXISTS run_log (
    id SERIAL PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    stored_count INTEGER NOT NULL DEFAULT 0,
    email_count INTEGER NOT NULL DEFAULT 0,
    source_stats TEXT NOT NULL DEFAULT '',
    errors TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    portal TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    attempted_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    apply_link TEXT NOT NULL,
    skills_csv TEXT NOT NULL,
    is_mnc INTEGER NOT NULL,
    is_product_based INTEGER NOT NULL,
    indian_cities_csv TEXT NOT NULL,
    salary TEXT NOT NULL,
    experience TEXT NOT NULL DEFAULT '',
    relevance_score REAL NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'not_applied',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    stored_count INTEGER NOT NULL DEFAULT 0,
    email_count INTEGER NOT NULL DEFAULT 0,
    source_stats TEXT NOT NULL DEFAULT '',
    errors TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    portal TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    attempted_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
"""


def init_db() -> None:
    if _USE_PG:
        conn = _pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(_PG_SCHEMA)
            # Migration: add experience column if missing
            cur.execute("""
                DO $$ BEGIN
                    ALTER TABLE jobs ADD COLUMN experience TEXT NOT NULL DEFAULT '';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            # Migration: add email_count column to run_log if missing
            cur.execute("""
                DO $$ BEGIN
                    ALTER TABLE run_log ADD COLUMN email_count INTEGER NOT NULL DEFAULT 0;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
            conn.commit()
            cur.close()
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        try:
            conn.executescript(_SQLITE_SCHEMA)
            # Migration: add experience column if missing
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN experience TEXT NOT NULL DEFAULT ''")
                conn.commit()
            except Exception:
                pass  # column already exists
            # Migration: add email_count column to run_log if missing
            try:
                conn.execute("ALTER TABLE run_log ADD COLUMN email_count INTEGER NOT NULL DEFAULT 0")
                conn.commit()
            except Exception:
                pass
        finally:
            conn.close()


# ── Query helpers ────────────────────────────────────────────────────────────

def _execute(cur, sql: str, params: tuple = ()):
    """Execute SQL, auto-translating ? to %s for PG."""
    if _USE_PG:
        sql = sql.replace("?", "%s")
        cur.execute(sql, params)
        return cur
    else:
        # cur is actually a sqlite3.Connection
        return cur.execute(sql, params)


def _fetchone(cur, sql: str, params: tuple = ()):
    result = _execute(cur, sql, params)
    if _USE_PG:
        return cur.fetchone()
    return result.fetchone()


def _fetchall(cur, sql: str, params: tuple = ()):
    result = _execute(cur, sql, params)
    if _USE_PG:
        return cur.fetchall()
    return result.fetchall()


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row or psycopg2 RealDictRow to dict."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


# ── Public API (used by pipeline, dashboard, etc.) ───────────────────────────

def fingerprint_exists(fp: str) -> bool:
    with _cursor() as cur:
        row = _fetchone(cur, "SELECT 1 FROM jobs WHERE fingerprint = ?", (fp,))
        return row is not None


def insert_job(job: EnrichedJob) -> int:
    sql = """
        INSERT INTO jobs (
            source, external_id, title, company, location, description, apply_link,
            skills_csv, is_mnc, is_product_based, indian_cities_csv, salary,
            experience, relevance_score, fingerprint, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        job.source,
        job.external_id,
        job.title,
        job.company,
        job.location,
        job.description,
        job.apply_link,
        ",".join(job.skills),
        int(job.is_mnc),
        int(job.is_product_based),
        ",".join(job.indian_cities),
        job.salary,
        job.experience,
        job.relevance_score,
        job.fingerprint,
        job.created_at.isoformat(),
    )
    if _USE_PG:
        conn = _pg_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql.replace("?", "%s") + " RETURNING id", params)
            row_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            return row_id
        finally:
            conn.close()
    else:
        conn = _sqlite_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()


def fetch_unsent_jobs(limit: int = 200) -> list[dict]:
    with _cursor() as cur:
        rows = _fetchall(cur, """
            SELECT * FROM jobs
            WHERE id NOT IN (
                SELECT job_id FROM applications WHERE status IN ('emailed','applied')
            )
            ORDER BY relevance_score DESC, id DESC
            LIMIT ?
        """, (limit,))
        return [_row_to_dict(r) for r in rows]


def fetch_all_jobs(query: str = "", limit: int = 500) -> list[dict]:
    with _cursor() as cur:
        rows = _fetchall(cur, """
            SELECT * FROM jobs
            WHERE lower(title) LIKE ? OR lower(company) LIKE ? OR lower(skills_csv) LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (f"%{query.lower()}%", f"%{query.lower()}%", f"%{query.lower()}%", limit))
        return [_row_to_dict(r) for r in rows]


def fetch_jobs_by_date(date_filter: str = "today", query: str = "", limit: int = 500) -> list[dict]:
    """Fetch jobs filtered by date bucket: today, yesterday, older."""
    if date_filter == "today":
        where_date = "AND DATE(created_at) = CURRENT_DATE"
    elif date_filter == "yesterday":
        where_date = "AND DATE(created_at) = CURRENT_DATE - INTERVAL '1 day'" if _USE_PG \
            else "AND DATE(created_at) = DATE('now', '-1 day')"
    else:  # older
        where_date = "AND DATE(created_at) < CURRENT_DATE - INTERVAL '1 day'" if _USE_PG \
            else "AND DATE(created_at) < DATE('now', '-1 day')"

    sql = f"""
        SELECT * FROM jobs
        WHERE (lower(title) LIKE ? OR lower(company) LIKE ? OR lower(skills_csv) LIKE ?)
        {where_date}
        ORDER BY id DESC LIMIT ?
    """
    with _cursor() as cur:
        rows = _fetchall(cur, sql,
                         (f"%{query.lower()}%", f"%{query.lower()}%", f"%{query.lower()}%", limit))
        return [_row_to_dict(r) for r in rows]


def fetch_date_counts() -> dict:
    """Return job counts for today, yesterday, older."""
    if _USE_PG:
        sql_today = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) = CURRENT_DATE"
        sql_yest = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) = CURRENT_DATE - INTERVAL '1 day'"
        sql_older = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) < CURRENT_DATE - INTERVAL '1 day'"
    else:
        sql_today = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) = DATE('now')"
        sql_yest = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) = DATE('now', '-1 day')"
        sql_older = "SELECT COUNT(*) as cnt FROM jobs WHERE DATE(created_at) < DATE('now', '-1 day')"

    with _cursor() as cur:
        today_count = _fetchone(cur, sql_today)
        today_count = today_count["cnt"] if isinstance(today_count, dict) else today_count[0]

        yest_count = _fetchone(cur, sql_yest)
        yest_count = yest_count["cnt"] if isinstance(yest_count, dict) else yest_count[0]

        older_count = _fetchone(cur, sql_older)
        older_count = older_count["cnt"] if isinstance(older_count, dict) else older_count[0]

    return {"today": today_count, "yesterday": yest_count, "older": older_count}


def fetch_applications(limit: int = 500) -> list[dict]:
    with _cursor() as cur:
        rows = _fetchall(cur, """
            SELECT a.*, j.title, j.company, j.apply_link
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            ORDER BY a.attempted_at DESC
            LIMIT ?
        """, (limit,))
        return [_row_to_dict(r) for r in rows]


def fetch_stats() -> dict:
    with _cursor() as cur:
        total = _fetchone(cur, "SELECT COUNT(*) as cnt FROM jobs")
        total = total["cnt"] if isinstance(total, dict) else total[0]

        applied = _fetchone(cur, "SELECT COUNT(*) as cnt FROM applications WHERE status='applied'")
        applied = applied["cnt"] if isinstance(applied, dict) else applied[0]

        emailed = _fetchone(cur, "SELECT COUNT(*) as cnt FROM applications WHERE status='emailed'")
        emailed = emailed["cnt"] if isinstance(emailed, dict) else emailed[0]

        failed = _fetchone(cur, "SELECT COUNT(*) as cnt FROM applications WHERE status='failed'")
        failed = failed["cnt"] if isinstance(failed, dict) else failed[0]

        sources = _fetchall(cur, "SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source ORDER BY cnt DESC")
        sources = [(_row_to_dict(r)["source"], _row_to_dict(r)["cnt"]) for r in sources]

        runs = _fetchall(cur, "SELECT * FROM run_log ORDER BY id DESC LIMIT 10")
        runs = [_row_to_dict(r) for r in runs]

        return {
            "total_jobs": total,
            "applied": applied,
            "emailed": emailed,
            "failed": failed,
            "sources": sources,
            "recent_runs": runs,
        }

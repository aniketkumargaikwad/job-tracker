from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from app.config import SETTINGS
from app.models import EnrichedJob

# Allow override for testing (set to ":memory:" or temp path)
_db_path_override: Optional[str] = None


def set_db_path(path: Optional[str]) -> None:
    """Override the database path. Use None to reset to default."""
    global _db_path_override
    _db_path_override = path


def get_conn() -> sqlite3.Connection:
    db_path = _db_path_override or str(SETTINGS.db_path)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
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
        )


def fingerprint_exists(fingerprint: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return row is not None


def insert_job(job: EnrichedJob) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (
                source, external_id, title, company, location, description, apply_link,
                skills_csv, is_mnc, is_product_based, indian_cities_csv, salary,
                relevance_score, fingerprint, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                job.relevance_score,
                job.fingerprint,
                job.created_at.isoformat(),
            ),
        )
        return int(cur.lastrowid)


def fetch_unsent_jobs(limit: int = 200) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM jobs
            WHERE id NOT IN (
                SELECT job_id FROM applications WHERE status IN ('emailed','applied')
            )
            ORDER BY relevance_score DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_all_jobs(query: str = "", limit: int = 500) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM jobs
            WHERE lower(title) LIKE ? OR lower(company) LIKE ? OR lower(skills_csv) LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (f"%{query.lower()}%", f"%{query.lower()}%", f"%{query.lower()}%", limit),
        ).fetchall()


def fetch_applications(limit: int = 500) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT a.*, j.title, j.company, j.apply_link
            FROM applications a
            JOIN jobs j ON j.id = a.job_id
            ORDER BY a.attempted_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM applications WHERE status='applied'").fetchone()[0]
        emailed = conn.execute("SELECT COUNT(*) FROM applications WHERE status='emailed'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM applications WHERE status='failed'").fetchone()[0]
        sources = conn.execute(
            "SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        runs = conn.execute(
            "SELECT * FROM run_log ORDER BY id DESC LIMIT 10"
        ).fetchall()
        return {
            "total_jobs": total,
            "applied": applied,
            "emailed": emailed,
            "failed": failed,
            "sources": [(r["source"], r["cnt"]) for r in sources],
            "recent_runs": runs,
        }

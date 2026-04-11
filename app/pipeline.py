"""Main pipeline – fetch → score → filter → dedupe → enrich → store → email.

Runs daily at 07:00 IST via scheduler.py or manually via CLI.
Never re-sends jobs that have been previously emailed or applied.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import SETTINGS
from app.db import fetch_unsent_jobs, fingerprint_exists, get_conn, init_db, insert_job, _USE_PG, _cursor, _execute
from app.emailer import send_email
from app.enrichment import enrich_job
from app.scoring import extract_skills, fingerprint, is_likely_duplicate, relevance_score
from app.sources.remote_sources import fetch_all_sources

log = logging.getLogger(__name__)


def _title_company_pairs() -> list[tuple[str, str]]:
    with _cursor() as cur:
        _execute(cur, "SELECT title, company FROM jobs")
        rows = cur.fetchall()
        return [(r["title"] if isinstance(r, dict) else r["title"],
                 r["company"] if isinstance(r, dict) else r["company"]) for r in rows]


def _should_keep(title: str, company: str, score: float) -> bool:
    title_l = title.lower()
    company_l = company.lower()
    if SETTINGS.title_blacklist and any(x.lower() in title_l for x in SETTINGS.title_blacklist):
        return False
    if SETTINGS.excluded_companies and any(x.lower() == company_l for x in SETTINGS.excluded_companies):
        return False
    return score >= 25


def run_pipeline(send_mail: bool = True) -> dict:
    init_db()
    started = datetime.now(timezone.utc).isoformat()

    # Insert run log entry
    if _USE_PG:
        import psycopg2
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO run_log(started_at, source_stats) VALUES (%s, %s) RETURNING id", (started, ""))
            run_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
        finally:
            conn.close()
    else:
        conn = get_conn()
        try:
            run_id = conn.execute(
                "INSERT INTO run_log(started_at, source_stats) VALUES (?, ?)", (started, "")
            ).lastrowid
            conn.commit()
        finally:
            conn.close()

    log.info("Pipeline started at %s", started)
    t0 = time.monotonic()

    # 1. Fetch from all sources
    raw_jobs = fetch_all_sources()
    t_fetch = time.monotonic()
    log.info("Fetched %d raw jobs from all sources (%.1fs)", len(raw_jobs), t_fetch - t0)

    # 2. FAST pre-filter by relevance score BEFORE expensive enrichment
    #    This avoids enriching hundreds of irrelevant jobs.
    existing_pairs = _title_company_pairs()
    candidates = []
    skipped_dup = 0
    skipped_filter = 0
    skipped_invalid = 0

    for raw in raw_jobs:
        if not raw.is_valid():
            skipped_invalid += 1
            continue

        # Quick relevance check using just title + description (no web calls)
        score = relevance_score(raw.description, raw.title)
        if not _should_keep(raw.title, raw.company, score):
            skipped_filter += 1
            continue

        if is_likely_duplicate(raw, existing_pairs):
            skipped_dup += 1
            continue

        # Quick fingerprint check before expensive enrichment
        fp = fingerprint(raw)
        if fingerprint_exists(fp):
            skipped_dup += 1
            continue

        candidates.append(raw)

    t_filter = time.monotonic()
    log.info("Pre-filter: %d candidates from %d raw (%.1fs) — "
             "skipped: %d irrelevant, %d dups, %d invalid",
             len(candidates), len(raw_jobs), t_filter - t_fetch,
             skipped_filter, skipped_dup, skipped_invalid)

    # 3. Enrich only the candidates that passed the filter
    saved = 0
    saved_jobs: list[dict] = []

    for raw in candidates:
        enriched = enrich_job(raw)
        try:
            insert_job(enriched)
            saved += 1
            existing_pairs.append((enriched.title, enriched.company))
            saved_jobs.append({
                "title": enriched.title,
                "company": enriched.company,
                "skills": ", ".join(enriched.skills),
                "is_mnc": "Yes" if enriched.is_mnc else "No",
                "is_product": "Yes" if enriched.is_product_based else "No",
                "cities": ", ".join(enriched.indian_cities) or "-",
                "salary": enriched.salary,
                "score": enriched.relevance_score,
                "source": enriched.source,
                "link": enriched.apply_link,
            })
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                skipped_dup += 1
            else:
                log.warning("Failed to insert %s @ %s: %s", enriched.title, enriched.company, exc)

    t_enrich = time.monotonic()
    log.info("Enriched & saved %d jobs (%.1fs)", saved, t_enrich - t_filter)

    # 4. Build digest of unsent jobs
    rows = fetch_unsent_jobs(limit=150)
    digest = []
    for r in rows:
        digest.append(
            {
                "job_id": r["id"],
                "title": r["title"],
                "company": r["company"],
                "skills": r["skills_csv"],
                "is_mnc": "Yes" if r["is_mnc"] else "No",
                "is_product": "Yes" if r["is_product_based"] else "No",
                "cities": r["indian_cities_csv"] or "—",
                "link": r["apply_link"],
                "salary": r["salary"],
            }
        )

    # 5. Send email digest
    if send_mail and digest:
        try:
            send_email(digest)
            log.info("Email sent with %d jobs", len(digest))
            with _cursor() as cur:
                for row in digest:
                    _execute(cur,
                        "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
                        (row["job_id"], "email_digest", "emailed", "", datetime.now(timezone.utc).isoformat()),
                    )
        except Exception as exc:
            log.error("Email send failed: %s", exc)

    # 6. Update run log
    t_total = time.monotonic() - t0
    with _cursor() as cur:
        _execute(cur,
            "UPDATE run_log SET finished_at = ?, fetched_count = ?, stored_count = ?, source_stats = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), len(raw_jobs), saved,
             f"dup={skipped_dup},filtered={skipped_filter},invalid={skipped_invalid}", run_id),
        )

    result = {
        "fetched": len(raw_jobs),
        "saved": saved,
        "skipped_dup": skipped_dup,
        "skipped_filter": skipped_filter,
        "skipped_invalid": skipped_invalid,
        "emailed": len(digest) if send_mail else 0,
        "time_seconds": round(t_total, 1),
        "jobs": saved_jobs,
    }
    log.info("Pipeline finished in %.1fs: fetched=%d saved=%d dup=%d filtered=%d",
             t_total, len(raw_jobs), saved, skipped_dup, skipped_filter)
    return result

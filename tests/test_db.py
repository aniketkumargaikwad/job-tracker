"""Tests for app.db – database operations (uses temp DB via conftest fixture)."""
import sqlite3

import pytest

from app.db import (
    fetch_all_jobs,
    fetch_applications,
    fetch_stats,
    fetch_unsent_jobs,
    fingerprint_exists,
    get_conn,
    init_db,
    insert_job,
)
from app.models import EnrichedJob


class TestInitDb:
    def test_tables_created(self):
        conn = get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        assert "jobs" in names
        assert "run_log" in names
        assert "applications" in names
        conn.close()

    def test_idempotent(self):
        # Calling init_db twice should not raise
        init_db()
        init_db()

    def test_indexes_created(self):
        conn = get_conn()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        names = {r["name"] for r in indexes}
        assert "idx_jobs_fingerprint" in names
        assert "idx_jobs_status" in names
        conn.close()


class TestInsertJob:
    def test_insert_returns_id(self, make_enriched_job):
        job = make_enriched_job()
        job_id = insert_job(job)
        assert isinstance(job_id, int)
        assert job_id >= 1

    def test_insert_stores_all_fields(self, make_enriched_job):
        job = make_enriched_job(
            title="Backend Dev",
            company="Acme",
            skills=["c#", ".net", "angular"],
            is_mnc=True,
            is_product_based=False,
            indian_cities=["Pune", "Mumbai"],
            salary="₹20 LPA",
            relevance_score=80.0,
        )
        job_id = insert_job(job)
        conn = get_conn()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        assert row["title"] == "Backend Dev"
        assert row["company"] == "Acme"
        assert row["skills_csv"] == "c#,.net,angular"
        assert row["is_mnc"] == 1
        assert row["is_product_based"] == 0
        assert row["indian_cities_csv"] == "Pune,Mumbai"
        assert row["salary"] == "₹20 LPA"
        assert row["relevance_score"] == 80.0

    def test_duplicate_fingerprint_raises(self, make_enriched_job):
        job = make_enriched_job(fingerprint="unique_fp_1")
        insert_job(job)
        job2 = make_enriched_job(fingerprint="unique_fp_1")
        with pytest.raises(sqlite3.IntegrityError):
            insert_job(job2)


class TestFingerprintExists:
    def test_exists_true(self, make_enriched_job):
        job = make_enriched_job(fingerprint="existing_fp")
        insert_job(job)
        assert fingerprint_exists("existing_fp") is True

    def test_exists_false(self):
        assert fingerprint_exists("nonexistent_fp") is False


class TestFetchUnsentJobs:
    def test_empty_db(self):
        rows = fetch_unsent_jobs()
        assert rows == []

    def test_returns_new_jobs(self, make_enriched_job):
        insert_job(make_enriched_job(fingerprint="fp1"))
        insert_job(make_enriched_job(fingerprint="fp2"))
        rows = fetch_unsent_jobs()
        assert len(rows) == 2

    def test_excludes_emailed_jobs(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_emailed")
        job_id = insert_job(job)
        conn = get_conn()
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "email", "emailed", "", "2026-01-01"),
        )
        conn.commit()
        conn.close()
        rows = fetch_unsent_jobs()
        assert len(rows) == 0

    def test_excludes_applied_jobs(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_applied")
        job_id = insert_job(job)
        conn = get_conn()
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "linkedin", "applied", "", "2026-01-01"),
        )
        conn.commit()
        conn.close()
        rows = fetch_unsent_jobs()
        assert len(rows) == 0

    def test_respects_limit(self, make_enriched_job):
        for i in range(10):
            insert_job(make_enriched_job(fingerprint=f"fp_limit_{i}"))
        rows = fetch_unsent_jobs(limit=3)
        assert len(rows) == 3

    def test_ordered_by_score_desc(self, make_enriched_job):
        insert_job(make_enriched_job(fingerprint="fp_low", relevance_score=30.0))
        insert_job(make_enriched_job(fingerprint="fp_high", relevance_score=90.0))
        rows = fetch_unsent_jobs()
        assert rows[0]["relevance_score"] >= rows[1]["relevance_score"]


class TestFetchAllJobs:
    def test_empty_db(self):
        rows = fetch_all_jobs()
        assert rows == []

    def test_search_by_title(self, make_enriched_job):
        insert_job(make_enriched_job(title="Angular Developer", company="AngCo",
                                      description="frontend work", skills=["angular", "typescript"],
                                      fingerprint="fp_angular"))
        insert_job(make_enriched_job(title="Java Developer", company="JavaCo",
                                      description="backend work", skills=["java", "spring"],
                                      fingerprint="fp_java"))
        rows = fetch_all_jobs("angular")
        assert len(rows) == 1
        assert rows[0]["title"] == "Angular Developer"

    def test_search_by_company(self, make_enriched_job):
        insert_job(make_enriched_job(company="Microsoft", fingerprint="fp_ms"))
        insert_job(make_enriched_job(company="Google", fingerprint="fp_google"))
        rows = fetch_all_jobs("microsoft")
        assert len(rows) == 1


class TestFetchApplications:
    def test_empty(self):
        assert fetch_applications() == []

    def test_returns_joined_data(self, make_enriched_job):
        job = make_enriched_job(title="Test Job", company="TestCo", fingerprint="fp_app_test")
        job_id = insert_job(job)
        conn = get_conn()
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "linkedin", "applied", "ok", "2026-04-01"),
        )
        conn.commit()
        conn.close()
        rows = fetch_applications()
        assert len(rows) == 1
        assert rows[0]["title"] == "Test Job"
        assert rows[0]["portal"] == "linkedin"


class TestFetchStats:
    def test_empty_db(self):
        stats = fetch_stats()
        assert stats["total_jobs"] == 0
        assert stats["applied"] == 0
        assert stats["emailed"] == 0
        assert stats["failed"] == 0
        assert stats["sources"] == []

    def test_with_data(self, make_enriched_job):
        insert_job(make_enriched_job(source="remotive", fingerprint="fp_stat1"))
        insert_job(make_enriched_job(source="remotive", fingerprint="fp_stat2"))
        insert_job(make_enriched_job(source="indeed_in", fingerprint="fp_stat3"))
        stats = fetch_stats()
        assert stats["total_jobs"] == 3
        assert len(stats["sources"]) == 2

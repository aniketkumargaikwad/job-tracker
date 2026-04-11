"""Shared pytest fixtures for the job automation test suite."""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.db import init_db, set_db_path
from app.models import EnrichedJob, RawJob


# ── Database fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _temp_db(tmp_path):
    """Every test gets its own fresh SQLite database."""
    db_file = str(tmp_path / "test_jobs.db")
    set_db_path(db_file)
    init_db()
    yield db_file
    set_db_path(None)


# ── Sample data factories ──────────────────────────────────────────────────

@pytest.fixture
def make_raw_job():
    """Factory to create RawJob instances with sane defaults."""
    _counter = 0

    def _factory(**overrides) -> RawJob:
        nonlocal _counter
        _counter += 1
        defaults = {
            "source": "test_source",
            "external_id": f"ext_{_counter}",
            "title": f"Senior .NET Developer #{_counter}",
            "company": f"TestCorp {_counter}",
            "location": "Remote",
            "description": "Looking for C# .NET Core Angular microservices developer with Azure experience",
            "apply_link": f"https://example.com/job/{_counter}",
            "posted_at": "2026-04-01",
            "salary_text": "",
        }
        defaults.update(overrides)
        return RawJob(**defaults)

    return _factory


@pytest.fixture
def make_enriched_job():
    """Factory to create EnrichedJob instances with sane defaults."""
    _counter = 0

    def _factory(**overrides) -> EnrichedJob:
        nonlocal _counter
        _counter += 1
        defaults = {
            "source": "test_source",
            "external_id": f"ext_{_counter}",
            "title": f"Senior .NET Developer #{_counter}",
            "company": f"TestCorp {_counter}",
            "location": "Remote",
            "description": "C# .NET Core Angular microservices",
            "apply_link": f"https://example.com/job/{_counter}",
            "skills": [".net core", "c#", "angular", "azure", "docker"],
            "is_mnc": False,
            "is_product_based": False,
            "indian_cities": [],
            "salary": "₹15-25 LPA",
            "relevance_score": 75.0,
            "fingerprint": f"fp_{_counter}_{_counter * 7}",
            "created_at": datetime.now(timezone.utc),
        }
        defaults.update(overrides)
        return EnrichedJob(**defaults)

    return _factory


@pytest.fixture
def sample_raw_job(make_raw_job):
    return make_raw_job()


@pytest.fixture
def sample_enriched_job(make_enriched_job):
    return make_enriched_job()


@pytest.fixture
def inserted_job(make_enriched_job):
    """Insert a job into the test DB and return (job, db_id)."""
    from app.db import insert_job
    job = make_enriched_job()
    db_id = insert_job(job)
    return job, db_id


# ── Email / SMTP fixtures ─────────────────────────────────────────────────

@pytest.fixture
def sample_email_rows():
    """Sample rows as they'd be built by the pipeline for email.send_email()."""
    return [
        {
            "job_id": 1,
            "title": "Senior .NET Developer",
            "company": "Microsoft",
            "skills": ".net core,c#,angular,azure,docker",
            "is_mnc": "Yes",
            "is_product": "Yes",
            "cities": "Bengaluru,Hyderabad",
            "link": "https://careers.microsoft.com/job/123",
            "salary": "₹25-45 LPA",
        },
        {
            "job_id": 2,
            "title": "Angular Developer",
            "company": "Acme Corp",
            "skills": "angular,typescript,c#",
            "is_mnc": "No",
            "is_product": "No",
            "cities": "—",
            "link": "https://acme.com/apply",
            "salary": "~₹12-22 LPA (estimated)",
        },
    ]

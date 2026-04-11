"""Tests for app.models – RawJob and EnrichedJob dataclasses."""
from datetime import datetime, timezone

from app.models import EnrichedJob, RawJob


class TestRawJob:
    def test_create_with_required_fields(self):
        job = RawJob("src", "1", "Dev", "Co", "Remote", "desc", "https://x.com")
        assert job.source == "src"
        assert job.title == "Dev"
        assert job.posted_at == ""
        assert job.salary_text == ""

    def test_create_with_all_fields(self):
        job = RawJob("src", "1", "Dev", "Co", "NYC", "desc", "https://x.com",
                      posted_at="2026-01-01", salary_text="100k")
        assert job.posted_at == "2026-01-01"
        assert job.salary_text == "100k"

    def test_is_valid_true(self):
        job = RawJob("src", "1", "Dev", "Co", "Remote", "desc", "https://x.com")
        assert job.is_valid() is True

    def test_is_valid_missing_title(self):
        job = RawJob("src", "1", "", "Co", "Remote", "desc", "https://x.com")
        assert job.is_valid() is False

    def test_is_valid_missing_company(self):
        job = RawJob("src", "1", "Dev", "", "Remote", "desc", "https://x.com")
        assert job.is_valid() is False

    def test_is_valid_missing_link(self):
        job = RawJob("src", "1", "Dev", "Co", "Remote", "desc", "")
        assert job.is_valid() is False

    def test_is_valid_all_empty(self):
        job = RawJob("src", "", "", "", "", "", "")
        assert job.is_valid() is False


class TestEnrichedJob:
    def test_create_with_defaults(self):
        job = EnrichedJob(
            source="s", external_id="1", title="T", company="C",
            location="L", description="D", apply_link="https://x.com",
            skills=["c#"], is_mnc=True, is_product_based=False,
            indian_cities=["Pune"], salary="10LPA", relevance_score=50.0,
            fingerprint="abc123",
        )
        assert isinstance(job.created_at, datetime)
        assert job.is_mnc is True
        assert job.skills == ["c#"]

    def test_created_at_is_auto_set(self):
        before = datetime.now(timezone.utc)
        job = EnrichedJob(
            source="s", external_id="1", title="T", company="C",
            location="L", description="D", apply_link="https://x.com",
            skills=[], is_mnc=False, is_product_based=False,
            indian_cities=[], salary="", relevance_score=0.0,
            fingerprint="fp",
        )
        after = datetime.now(timezone.utc)
        assert before <= job.created_at <= after

    def test_custom_created_at(self):
        custom = datetime(2025, 1, 1)
        job = EnrichedJob(
            source="s", external_id="1", title="T", company="C",
            location="L", description="D", apply_link="https://x.com",
            skills=[], is_mnc=False, is_product_based=False,
            indian_cities=[], salary="", relevance_score=0.0,
            fingerprint="fp", created_at=custom,
        )
        assert job.created_at == custom

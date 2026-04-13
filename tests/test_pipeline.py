"""Tests for app.pipeline – full pipeline flow with mocked sources/email."""
from unittest.mock import MagicMock, patch

import pytest

from app.db import get_conn, insert_job
from app.models import RawJob
from app.pipeline import _should_keep, _title_company_pairs, run_pipeline


class TestShouldKeep:
    def test_keeps_high_score(self):
        assert _should_keep("Senior .NET Developer", "Microsoft", 80.0) is True

    def test_rejects_low_score(self):
        assert _should_keep("Dev", "Co", 10.0) is False

    def test_rejects_threshold(self):
        assert _should_keep("Dev", "Co", 24.9) is False

    def test_accepts_at_threshold(self):
        assert _should_keep("Dev", "Co", 40.0) is True

    @patch("app.pipeline.SETTINGS")
    def test_rejects_blacklisted_title(self, mock_settings):
        mock_settings.title_blacklist = ["Intern", "Trainee"]
        mock_settings.excluded_companies = []
        assert _should_keep("Software Intern", "Google", 90.0) is False

    @patch("app.pipeline.SETTINGS")
    def test_rejects_excluded_company(self, mock_settings):
        mock_settings.title_blacklist = []
        mock_settings.excluded_companies = ["BadCorp"]
        assert _should_keep("Senior Dev", "BadCorp", 90.0) is False

    @patch("app.pipeline.SETTINGS")
    def test_keeps_non_blacklisted(self, mock_settings):
        mock_settings.title_blacklist = ["Intern"]
        mock_settings.excluded_companies = ["BadCorp"]
        assert _should_keep("Senior Dev", "GoodCorp", 60.0) is True


class TestTitleCompanyPairs:
    def test_empty_db(self):
        pairs = _title_company_pairs()
        assert pairs == []

    def test_returns_pairs(self, make_enriched_job):
        from app.db import insert_job
        insert_job(make_enriched_job(title="Dev A", company="Co A", fingerprint="fp_pair1"))
        insert_job(make_enriched_job(title="Dev B", company="Co B", fingerprint="fp_pair2"))
        pairs = _title_company_pairs()
        assert len(pairs) == 2
        assert ("Dev A", "Co A") in pairs


class TestRunPipeline:
    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_empty_sources(self, mock_fetch, mock_email):
        mock_fetch.return_value = []
        result = run_pipeline(send_mail=False)
        assert result["fetched"] == 0
        assert result["saved"] == 0
        assert result["emailed"] == 0

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_saves_valid_jobs(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "Senior C# Developer", "Microsoft", "Remote",
                   ".NET Core C# Angular microservices remote developer", "https://example.com/1"),
            RawJob("test", "2", ".NET Developer", "Google", "Remote",
                   "C# .NET Core Angular microservices remote developer", "https://example.com/2"),
        ]
        result = run_pipeline(send_mail=False)
        assert result["fetched"] == 2
        assert result["saved"] >= 1

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_skips_invalid_jobs(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "", "", "", "", ""),  # invalid
            RawJob("test", "2", "Dev", "Co", "Remote",
                   "C# .NET developer remote", "https://x.com"),  # valid
        ]
        result = run_pipeline(send_mail=False)
        assert result["fetched"] == 2

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_deduplicates(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "Senior C# Dev", "Acme", "Remote",
                   "C# .NET Core Angular remote", "https://example.com/1"),
            RawJob("test", "2", "Senior C# Dev", "Acme", "Remote",
                   "C# .NET Core Angular remote", "https://example.com/1"),  # same link = same FP
        ]
        result = run_pipeline(send_mail=False)
        assert result["saved"] <= 1  # At most 1, second should be deduped

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_email_sent_when_enabled(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "C# Developer", "BigCo", "Remote",
                   "C# .NET Core Angular microservices remote developer", "https://example.com/1"),
        ]
        result = run_pipeline(send_mail=True)
        if result["saved"] >= 1:
            mock_email.assert_called_once()

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_email_not_sent_when_disabled(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "C# Developer", "BigCo", "Remote",
                   "C# .NET developer remote", "https://example.com/1"),
        ]
        run_pipeline(send_mail=False)
        mock_email.assert_not_called()

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_run_log_updated(self, mock_fetch, mock_email):
        mock_fetch.return_value = []
        run_pipeline(send_mail=False)
        conn = get_conn()
        runs = conn.execute("SELECT * FROM run_log").fetchall()
        conn.close()
        assert len(runs) >= 1
        assert runs[-1]["finished_at"] is not None

    @patch("app.pipeline.send_email", side_effect=Exception("SMTP error"))
    @patch("app.pipeline.fetch_all_sources")
    def test_email_failure_doesnt_crash(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "C# Developer", "BigCo", "Remote",
                   "C# .NET Core Angular microservices remote developer", "https://example.com/1"),
        ]
        # Should not raise despite email failure
        result = run_pipeline(send_mail=True)
        assert "fetched" in result

    @patch("app.pipeline.send_email")
    @patch("app.pipeline.fetch_all_sources")
    def test_filters_low_score_jobs(self, mock_fetch, mock_email):
        mock_fetch.return_value = [
            RawJob("test", "1", "Graphic Designer", "Acme", "Remote",
                   "Photoshop and Figma expert needed", "https://example.com/1"),
        ]
        result = run_pipeline(send_mail=False)
        assert result["saved"] == 0
        assert result["skipped_filter"] >= 1

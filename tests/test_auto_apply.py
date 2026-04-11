"""Tests for app.auto_apply – mark_failed, mark_applied, apply_to_job."""
from unittest.mock import MagicMock, patch

import pytest

from app.auto_apply import apply_to_job, mark_applied, mark_failed
from app.db import get_conn, insert_job


class TestMarkFailed:
    def test_updates_job_status(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_fail1")
        job_id = insert_job(job)
        mark_failed(job_id, "adapter not available")
        conn = get_conn()
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        assert row["status"] == "failed"

    def test_creates_application_record(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_fail2")
        job_id = insert_job(job)
        mark_failed(job_id, "some reason")
        conn = get_conn()
        app_row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        assert app_row["status"] == "failed"
        assert app_row["details"] == "some reason"


class TestMarkApplied:
    def test_updates_job_status(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_applied1")
        job_id = insert_job(job)
        mark_applied(job_id, "linkedin.com", "Easy Apply")
        conn = get_conn()
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        assert row["status"] == "applied"

    def test_creates_application_record(self, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_applied2")
        job_id = insert_job(job)
        mark_applied(job_id, "naukri.com")
        conn = get_conn()
        app_row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        assert app_row["status"] == "applied"
        assert app_row["portal"] == "naukri.com"


class TestApplyToJob:
    def test_job_not_found(self):
        result = apply_to_job(99999)
        assert result == "job_not_found"

    @patch("app.auto_apply._get_browser", return_value=(None, None))
    def test_no_browser_available(self, mock_browser, make_enriched_job):
        job = make_enriched_job(
            apply_link="https://linkedin.com/jobs/123",
            fingerprint="fp_no_browser",
        )
        job_id = insert_job(job)
        result = apply_to_job(job_id)
        assert result == "failed_no_browser"
        # Verify it was marked as failed in DB
        conn = get_conn()
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        assert row["status"] == "failed"

    @patch("app.auto_apply._get_browser")
    def test_linkedin_adapter_selected(self, mock_browser, make_enriched_job):
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_pw = MagicMock()
        mock_bro = MagicMock()
        mock_bro.new_page.return_value = mock_page
        mock_browser.return_value = (mock_pw, mock_bro)

        job = make_enriched_job(
            apply_link="https://www.linkedin.com/jobs/view/123",
            fingerprint="fp_linkedin_test",
        )
        job_id = insert_job(job)
        result = apply_to_job(job_id)
        assert "linkedin" in result.lower() or "applied" in result.lower()
        mock_page.goto.assert_called_once()

    @patch("app.auto_apply._get_browser")
    def test_indeed_adapter_selected(self, mock_browser, make_enriched_job):
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_pw = MagicMock()
        mock_bro = MagicMock()
        mock_bro.new_page.return_value = mock_page
        mock_browser.return_value = (mock_pw, mock_bro)

        job = make_enriched_job(
            apply_link="https://www.indeed.com/viewjob?jk=abc123",
            fingerprint="fp_indeed_test",
        )
        job_id = insert_job(job)
        result = apply_to_job(job_id)
        assert "indeed" in result.lower() or "applied" in result.lower()

    @patch("app.auto_apply._get_browser")
    def test_generic_adapter_for_unknown_portal(self, mock_browser, make_enriched_job):
        mock_page = MagicMock()
        mock_page.query_selector.return_value = None
        mock_pw = MagicMock()
        mock_bro = MagicMock()
        mock_bro.new_page.return_value = mock_page
        mock_browser.return_value = (mock_pw, mock_bro)

        job = make_enriched_job(
            apply_link="https://unknown-portal.com/apply/123",
            fingerprint="fp_generic_test",
        )
        job_id = insert_job(job)
        result = apply_to_job(job_id)
        assert "generic" in result.lower() or "applied" in result.lower()

    @patch("app.auto_apply._get_browser")
    def test_browser_exception_marks_failed(self, mock_browser, make_enriched_job):
        mock_pw = MagicMock()
        mock_bro = MagicMock()
        mock_bro.new_page.side_effect = Exception("browser crashed")
        mock_browser.return_value = (mock_pw, mock_bro)

        job = make_enriched_job(
            apply_link="https://example.com/job/1",
            fingerprint="fp_crash_test",
        )
        job_id = insert_job(job)
        result = apply_to_job(job_id)
        assert "failed" in result.lower()


class TestFillCommonFields:
    def test_fills_matching_fields(self):
        from app.auto_apply import _fill_common_fields

        mock_page = MagicMock()
        mock_el = MagicMock()
        mock_page.query_selector.return_value = mock_el

        with patch("app.auto_apply.PROFILE") as mock_profile:
            mock_profile.full_name = "John Doe"
            mock_profile.email = "john@test.com"
            mock_profile.phone = "+91-123"
            _fill_common_fields(mock_page, {
                "name": 'input[name="name"]',
                "email": 'input[type="email"]',
            })
            assert mock_el.fill.call_count >= 1

    def test_skips_empty_values(self):
        from app.auto_apply import _fill_common_fields

        mock_page = MagicMock()
        with patch("app.auto_apply.PROFILE") as mock_profile:
            mock_profile.full_name = ""
            mock_profile.email = ""
            mock_profile.phone = ""
            mock_profile.experience_years = ""
            mock_profile.current_company = ""
            mock_profile.current_title = ""
            mock_profile.linkedin = ""
            mock_profile.github = ""
            mock_profile.location = ""
            mock_profile.expected_salary = ""
            mock_profile.notice_period = ""
            mock_profile.skills = ""
            _fill_common_fields(mock_page, {"name": 'input[name="name"]'})
            mock_page.query_selector.assert_not_called()


class TestUploadResume:
    @patch("app.auto_apply.PROFILE")
    def test_skips_missing_file(self, mock_profile):
        from app.auto_apply import _upload_resume
        mock_profile.resume_path = "/nonexistent/resume.pdf"
        mock_page = MagicMock()
        _upload_resume(mock_page, 'input[type="file"]')
        mock_page.set_input_files.assert_not_called()

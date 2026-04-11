"""Tests for app.emailer – HTML builder and send_email."""
from unittest.mock import MagicMock, patch

import pytest

from app.emailer import _esc, build_html, send_email


class TestEsc:
    def test_escapes_html(self):
        assert _esc("<script>alert('xss')</script>") == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"

    def test_escapes_ampersand(self):
        assert "&amp;" in _esc("A & B")

    def test_escapes_quotes(self):
        result = _esc('He said "hello"')
        assert "&quot;" in result or "&#x27;" in result or '"' not in result

    def test_passes_through_normal_text(self):
        assert _esc("Hello World") == "Hello World"

    def test_converts_non_string(self):
        assert _esc(42) == "42"


class TestBuildHtml:
    def test_returns_html_string(self, sample_email_rows):
        html = build_html(sample_email_rows)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_all_columns(self, sample_email_rows):
        html = build_html(sample_email_rows)
        assert "Sr.No" in html
        assert "Job Title" in html
        assert "Company" in html
        assert "5 Key Skills" in html
        assert "MNC?" in html
        assert "Product?" in html
        assert "Indian Cities" in html
        assert "Apply" in html
        assert "Salary" in html

    def test_contains_job_data(self, sample_email_rows):
        html = build_html(sample_email_rows)
        assert "Senior .NET Developer" in html
        assert "Microsoft" in html
        assert "₹25-45 LPA" in html

    def test_contains_apply_buttons(self, sample_email_rows):
        html = build_html(sample_email_rows)
        assert "Quick Apply" in html
        assert "Portal" in html

    def test_row_count_matches(self, sample_email_rows):
        html = build_html(sample_email_rows)
        assert "2 new jobs found" in html

    def test_empty_rows(self):
        html = build_html([])
        assert "0 new jobs found" in html

    def test_xss_prevention(self):
        rows = [{
            "job_id": 1,
            "title": '<script>alert("xss")</script>',
            "company": "Safe&Co",
            "skills": "c#",
            "is_mnc": "No",
            "is_product": "No",
            "cities": "—",
            "link": "https://example.com",
            "salary": "10LPA",
        }]
        html = build_html(rows)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "Safe&amp;Co" in html


class TestSendEmail:
    def test_skips_if_no_rows(self):
        # Should not raise even with empty rows
        send_email([])

    @patch("app.emailer.SETTINGS")
    def test_skips_if_no_host(self, mock_settings):
        mock_settings.email_host = ""
        send_email([{"title": "test"}])
        # No exception = passes

    @patch("app.emailer.smtplib.SMTP")
    @patch("app.emailer.SETTINGS")
    def test_sends_email_successfully(self, mock_settings, mock_smtp_class, sample_email_rows):
        mock_settings.email_host = "smtp.test.com"
        mock_settings.email_port = 587
        mock_settings.email_user = "user@test.com"
        mock_settings.email_password = "pass"
        mock_settings.email_from = "from@test.com"
        mock_settings.email_to = "to@test.com"
        mock_settings.dashboard_host = "127.0.0.1"
        mock_settings.dashboard_port = 5000

        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        send_email(sample_email_rows)

        mock_smtp_class.assert_called_once_with("smtp.test.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@test.com", "pass")
        mock_server.sendmail.assert_called_once()

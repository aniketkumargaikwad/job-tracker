"""Tests for app.sources.scraper_sources – web scraping connectors (mocked HTTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.sources.scraper_sources import (
    SCRAPER_SOURCES,
    fetch_duckduckgo_jobs,
    fetch_indeed_all,
    fetch_linkedin,
    fetch_shine,
)


_EMPTY_HTML = "<html><body></body></html>"


class TestFetchLinkedin:
    @patch("app.sources.scraper_sources._get_html")
    def test_parses_cards(self, mock_html):
        from bs4 import BeautifulSoup
        html = """
        <html><body>
        <div class="base-card">
            <h3 class="base-search-card__title">.NET Developer</h3>
            <h4 class="base-search-card__subtitle">Microsoft</h4>
            <span class="job-search-card__location">Remote</span>
            <a class="base-card__full-link" href="https://linkedin.com/jobs/view/123">Link</a>
        </div>
        </body></html>
        """
        mock_html.return_value = BeautifulSoup(html, "html.parser")
        jobs = fetch_linkedin()
        assert len(jobs) >= 1
        assert jobs[0].source == "linkedin"
        assert jobs[0].title == ".NET Developer"

    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("blocked"))
    def test_handles_failure(self, mock_html):
        jobs = fetch_linkedin()
        assert jobs == []


class TestFetchIndeed:
    @patch("app.sources.scraper_sources._session")
    def test_handles_failure_gracefully(self, mock_session):
        mock_session.get.side_effect = Exception("blocked")
        jobs = fetch_indeed_all()
        assert jobs == []

    @patch("app.sources.scraper_sources.time.sleep")
    @patch("app.sources.scraper_sources._session")
    def test_returns_empty_on_no_cards(self, mock_session, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<rss><channel></channel></rss>"
        mock_session.get.return_value = mock_resp
        jobs = fetch_indeed_all()
        assert jobs == []


class TestFetchShine:
    @patch("app.sources.scraper_sources._session")
    def test_handles_failure(self, mock_session):
        mock_session.get.side_effect = Exception("timeout")
        jobs = fetch_shine()
        assert jobs == []

    @patch("app.sources.scraper_sources.time.sleep")
    @patch("app.sources.scraper_sources._session")
    def test_parses_cards(self, mock_session, mock_sleep):
        html = """<html><body>
        <div class="jdbigCard" itemprop="itemListElement" itemscope>
            <span class="jobCardNova_postedData__LTERc">posted 1 day ago</span>
            <meta content="https://www.shine.com/jobs/net-dev/acme/12345" itemprop="url"/>
            <h3 itemprop="name"><a href="https://www.shine.com/jobs/net-dev/acme/12345">.NET Developer</a></h3>
            <span class="jdTruncationCompany">Acme Corp</span>
            <div class="jobCardNova_bigCardLocation__OMkI1"><span>Pune</span></div>
            <div class="jdSkills"><li>C#</li><li>Azure</li></div>
        </div>
        </body></html>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_session.get.return_value = mock_resp
        jobs = fetch_shine()
        assert len(jobs) >= 1
        assert jobs[0].source == "shine"
        assert jobs[0].title == ".NET Developer"
        assert jobs[0].company == "Acme Corp"


class TestFetchDuckDuckGo:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_duckduckgo_jobs() == []


class TestScraperSourceRegistration:
    def test_all_sources_registered(self):
        names = [name for name, _ in SCRAPER_SOURCES]
        assert "linkedin" in names
        assert "shine" in names
        assert "indeed_rss" in names
        assert "duckduckgo" in names

    def test_source_count(self):
        assert len(SCRAPER_SOURCES) == 5

    def test_all_callables(self):
        for name, fn in SCRAPER_SOURCES:
            assert callable(fn), f"{name} is not callable"

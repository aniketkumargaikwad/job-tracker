"""Tests for app.sources.scraper_sources – web scraping connectors (mocked HTTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.sources.scraper_sources import (
    SCRAPER_SOURCES,
    fetch_bayt,
    fetch_cwjobs,
    fetch_duckduckgo_jobs,
    fetch_glassdoor,
    fetch_gulftalet,
    fetch_indeed_all,
    fetch_linkedin,
    fetch_naukri,
    fetch_simplyhired,
    fetch_wellfound,
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
    @patch("app.sources.scraper_sources._get_html")
    def test_handles_failure_gracefully(self, mock_html):
        mock_html.side_effect = Exception("blocked")
        jobs = fetch_indeed_all()
        assert jobs == []

    @patch("app.sources.scraper_sources._get_html")
    def test_returns_empty_on_no_cards(self, mock_html):
        from bs4 import BeautifulSoup
        mock_html.return_value = BeautifulSoup(_EMPTY_HTML, "html.parser")
        jobs = fetch_indeed_all()
        assert jobs == []


class TestFetchNaukri:
    @patch("app.sources.scraper_sources._get_html")
    def test_handles_failure(self, mock_html):
        mock_html.side_effect = Exception("timeout")
        jobs = fetch_naukri()
        assert jobs == []

    @patch("app.sources.scraper_sources._get_html")
    def test_returns_empty(self, mock_html):
        from bs4 import BeautifulSoup
        mock_html.return_value = BeautifulSoup(_EMPTY_HTML, "html.parser")
        jobs = fetch_naukri()
        assert jobs == []


class TestFetchSimplyHired:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_simplyhired() == []


class TestFetchGulfTalent:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_gulftalet() == []


class TestFetchBayt:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_bayt() == []


class TestFetchCWJobs:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_cwjobs() == []


class TestFetchWellfound:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_wellfound() == []


class TestFetchGlassdoor:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_glassdoor() == []


class TestFetchDuckDuckGo:
    @patch("app.sources.scraper_sources._get_html", side_effect=Exception("err"))
    def test_handles_failure(self, mock_html):
        assert fetch_duckduckgo_jobs() == []


class TestScraperSourceRegistration:
    def test_all_sources_registered(self):
        names = [name for name, _ in SCRAPER_SOURCES]
        assert "linkedin" in names
        assert "indeed_all" in names
        assert "naukri" in names
        assert "simplyhired" in names
        assert "gulftalet" in names
        assert "bayt" in names
        assert "cwjobs" in names
        assert "wellfound" in names
        assert "glassdoor" in names
        assert "duckduckgo" in names

    def test_source_count(self):
        assert len(SCRAPER_SOURCES) == 10

    def test_all_callables(self):
        for name, fn in SCRAPER_SOURCES:
            assert callable(fn), f"{name} is not callable"

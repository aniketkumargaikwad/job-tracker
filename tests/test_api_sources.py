"""Tests for app.sources.api_sources – API source connectors (mocked HTTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.sources.api_sources import (
    KEYED_API_SOURCES,
    OPEN_API_SOURCES,
    fetch_arbeitnow,
    fetch_himalayas,
    fetch_jobicy,
    fetch_remoteok,
    fetch_remotive,
    fetch_themuse,
)


class TestFetchRemotive:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {
            "jobs": [
                {
                    "id": 1, "title": ".NET Dev", "company_name": "Acme",
                    "candidate_required_location": "Remote", "description": "C# dev",
                    "url": "https://remotive.com/1", "publication_date": "2026-01-01",
                    "salary": "$80k",
                }
            ]
        })
        jobs = fetch_remotive()
        assert len(jobs) >= 1
        assert jobs[0].source == "remotive"
        assert jobs[0].title == ".NET Dev"
        assert jobs[0].salary_text == "$80k"

    @patch("app.sources.api_sources._get", side_effect=Exception("timeout"))
    def test_handles_failure(self, mock_get):
        jobs = fetch_remotive()
        assert jobs == []

    @patch("app.sources.api_sources._get")
    def test_empty_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {"jobs": []})
        jobs = fetch_remotive()
        assert jobs == []


class TestFetchRemoteOK:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: [
            {"legal": "info"},
            {"id": 1, "position": ".NET Developer", "company": "TestCo",
             "location": "Remote", "description": "C# needed",
             "url": "https://remoteok.com/1", "date": "2026-01-01",
             "salary_min": "80000", "salary_max": "120000"},
        ])
        jobs = fetch_remoteok()
        assert len(jobs) >= 1
        assert jobs[0].source == "remoteok"

    @patch("app.sources.api_sources._get", side_effect=Exception("blocked"))
    def test_handles_failure(self, mock_get):
        jobs = fetch_remoteok()
        assert jobs == []


class TestFetchArbeitnow:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {
            "data": [
                {"slug": "job-1", "title": "C# Dev", "company_name": "FirmX",
                 "location": "Remote", "description": "Angular", "url": "https://arbeitnow.com/1",
                 "created_at": "2026-01-01", "remote": True}
            ]
        })
        jobs = fetch_arbeitnow()
        assert len(jobs) >= 1
        assert jobs[0].source == "arbeitnow"

    @patch("app.sources.api_sources._get")
    def test_handles_empty_pages(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {"data": []})
        jobs = fetch_arbeitnow()
        assert jobs == []


class TestFetchHimalayas:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {
            "jobs": [
                {"id": 1, "title": ".NET Dev", "companyName": "HCo",
                 "location": "Remote", "description": "desc",
                 "applicationLink": "https://himalayas.app/1",
                 "pubDate": "2026-01-01", "minSalary": "60000", "maxSalary": "100000"}
            ]
        })
        jobs = fetch_himalayas()
        assert len(jobs) >= 1
        assert jobs[0].source == "himalayas"


class TestFetchJobicy:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {
            "jobs": [
                {"id": 1, "jobTitle": "Backend Dev", "companyName": "JCo",
                 "jobGeo": "Worldwide", "jobDescription": "C#",
                 "url": "https://jobicy.com/1", "pubDate": "2026-01-01",
                 "annualSalaryMin": "50000", "annualSalaryMax": "90000"}
            ]
        })
        jobs = fetch_jobicy()
        assert len(jobs) >= 1


class TestFetchTheMuse:
    @patch("app.sources.api_sources._get")
    def test_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(json=lambda: {
            "results": [
                {"id": 1, "name": "Software Eng", "company": {"name": "MCo"},
                 "locations": [{"name": "Remote"}], "contents": ".NET description",
                 "refs": {"landing_page": "https://themuse.com/1"},
                 "publication_date": "2026-01-01"}
            ]
        })
        jobs = fetch_themuse()
        assert len(jobs) >= 1


class TestSourceRegistration:
    def test_open_sources_registered(self):
        names = [name for name, _ in OPEN_API_SOURCES]
        assert "remotive" in names
        assert "arbeitnow" in names
        assert "himalayas" in names
        assert "jobicy" in names
        assert "themuse" in names

    def test_keyed_sources_registered(self):
        names = [name for name, _ in KEYED_API_SOURCES]
        assert "adzuna_multi" in names
        assert "reed" in names
        assert "jooble" in names

    def test_all_sources_callable(self):
        for name, fn in OPEN_API_SOURCES + KEYED_API_SOURCES:
            assert callable(fn), f"{name} is not callable"


class TestKeyedSourcesSkipWithoutKeys:
    @patch.dict("os.environ", {}, clear=False)
    def test_adzuna_skips_without_keys(self):
        import os
        os.environ.pop("ADZUNA_APP_ID", None)
        os.environ.pop("ADZUNA_APP_KEY", None)
        from app.sources.api_sources import fetch_adzuna
        jobs = fetch_adzuna("in")
        assert jobs == []

    @patch.dict("os.environ", {}, clear=False)
    def test_reed_skips_without_key(self):
        import os
        os.environ.pop("REED_API_KEY", None)
        from app.sources.api_sources import fetch_reed
        jobs = fetch_reed()
        assert jobs == []

    @patch.dict("os.environ", {}, clear=False)
    def test_jooble_skips_without_key(self):
        import os
        os.environ.pop("JOOBLE_API_KEY", None)
        from app.sources.api_sources import fetch_jooble
        jobs = fetch_jooble()
        assert jobs == []

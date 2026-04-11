"""Tests for app.sources.remote_sources – master source orchestrator."""
from unittest.mock import MagicMock, patch

import pytest

from app.models import RawJob
from app.sources.remote_sources import fetch_all_sources


class TestFetchAllSources:
    @patch("app.sources.remote_sources.SCRAPER_SOURCES", [])
    @patch("app.sources.remote_sources.KEYED_API_SOURCES", [])
    @patch("app.sources.remote_sources.OPEN_API_SOURCES", [])
    def test_empty_sources(self):
        jobs = fetch_all_sources()
        assert jobs == []

    @patch("app.sources.remote_sources.SCRAPER_SOURCES", [])
    @patch("app.sources.remote_sources.KEYED_API_SOURCES", [])
    @patch("app.sources.remote_sources.OPEN_API_SOURCES", [
        ("test_src", lambda: [
            RawJob("test", "1", "Dev", "Co", "Remote", "desc", "https://x.com"),
        ]),
    ])
    def test_collects_from_api_sources(self):
        jobs = fetch_all_sources()
        assert len(jobs) == 1
        assert jobs[0].source == "test"

    @patch("app.sources.remote_sources.SCRAPER_SOURCES", [])
    @patch("app.sources.remote_sources.KEYED_API_SOURCES", [])
    def test_survives_source_failure(self):
        def _failing():
            raise Exception("source crashed")

        with patch("app.sources.remote_sources.OPEN_API_SOURCES", [
            ("good_src", lambda: [RawJob("good", "1", "Dev", "Co", "Remote", "d", "https://x.com")]),
            ("bad_src", _failing),
        ]):
            jobs = fetch_all_sources()
            assert len(jobs) == 1  # good_src succeeds, bad_src fails gracefully

    @patch("app.sources.remote_sources.SCRAPER_SOURCES", [
        ("scraper1", lambda: [RawJob("s1", "1", "Dev", "Co", "Remote", "d", "https://x.com")]),
    ])
    @patch("app.sources.remote_sources.KEYED_API_SOURCES", [
        ("keyed1", lambda: [RawJob("k1", "1", "Dev", "Co", "Remote", "d", "https://y.com")]),
    ])
    @patch("app.sources.remote_sources.OPEN_API_SOURCES", [
        ("api1", lambda: [RawJob("a1", "1", "Dev", "Co", "Remote", "d", "https://z.com")]),
    ])
    def test_combines_all_tiers(self):
        jobs = fetch_all_sources()
        assert len(jobs) == 3
        sources = {j.source for j in jobs}
        assert sources == {"a1", "k1", "s1"}

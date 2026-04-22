"""Tests for app.web_dashboard – Flask routes and APIs."""
from unittest.mock import MagicMock, patch

import pytest

from app.db import get_conn, insert_job
from app.web_dashboard import app


@pytest.fixture
def client():
    """Flask test client with test DB."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestIndexRoute:
    def test_redirects_to_today(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/jobs/today" in resp.headers.get("Location", "")

    def test_today_returns_200(self, client):
        resp = client.get("/jobs/today")
        assert resp.status_code == 200

    def test_contains_terminal_theme(self, client):
        resp = client.get("/jobs/today")
        html = resp.data.decode()
        assert "Remote" in html

    def test_empty_db(self, client):
        resp = client.get("/jobs/today")
        assert resp.status_code == 200


class TestHistoryRoute:
    def test_returns_200(self, client):
        resp = client.get("/history")
        assert resp.status_code == 200

    def test_contains_history_table(self, client):
        html = client.get("/history").data.decode()
        assert "Application History" in html
        assert "Portal" in html

    def test_shows_application_data(self, client, make_enriched_job):
        job = make_enriched_job(title="Test Job", company="TestCo", fingerprint="fp_hist1")
        job_id = insert_job(job)
        conn = get_conn()
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "linkedin", "applied", "ok", "2026-04-01"),
        )
        conn.commit()
        conn.close()
        html = client.get("/history").data.decode()
        assert "Test Job" in html
        assert "linkedin" in html


class TestStatsRoute:
    def test_returns_200(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_contains_stat_cards(self, client):
        html = client.get("/stats").data.decode()
        assert "Total Jobs" in html
        assert "Applied" in html
        assert "Emailed" in html

    def test_with_data(self, client, make_enriched_job):
        insert_job(make_enriched_job(source="remotive", fingerprint="fp_stat_w1"))
        insert_job(make_enriched_job(source="indeed_in", fingerprint="fp_stat_w2"))
        html = client.get("/stats").data.decode()
        assert "remotive" in html


class TestAutoApplyRoute:
    def test_redirects_to_apply_link(self, client, make_enriched_job):
        job = make_enriched_job(fingerprint="fp_auto1")
        job_id = insert_job(job)
        resp = client.get(f"/apply/{job_id}")
        assert resp.status_code == 302

    def test_nonexistent_job(self, client):
        resp = client.get("/apply/99999")
        assert resp.status_code == 404


class TestApiJobs:
    def test_returns_json(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        data = resp.get_json()
        assert isinstance(data, list)

    def test_search_filter(self, client, make_enriched_job):
        insert_job(make_enriched_job(title="API Test Job", fingerprint="fp_api1"))
        resp = client.get("/api/jobs?q=api+test")
        data = resp.get_json()
        assert len(data) >= 1


class TestApiTriggerRun:
    def test_trigger_returns_json(self, client):
        resp = client.get("/api/trigger-run")
        assert resp.status_code == 200
        # Streaming ndjson — first line is {"status": "started"}
        import json
        lines = [l for l in resp.data.decode().strip().splitlines() if l.strip()]
        first = json.loads(lines[0])
        assert first["status"] == "started"

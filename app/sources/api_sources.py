"""Free-API job sources (no credit card required).

Tier 1 – completely open APIs:
    Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, The Muse, JoBoard

Tier 2 – free API key (register, no CC):
    Adzuna (multi-country), Reed.co.uk, Jooble
"""
from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Any
from urllib.parse import quote_plus

import requests

from app.models import RawJob

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

SEARCH_TERMS = [
    ".net developer",
    "c# developer",
    "dotnet",
    ".net core",
    "asp.net",
    "angular developer",
    "microservices c#",
    "azure .net",
    "full stack .net",
    "backend c#",
    "entity framework",
    "blazor",
]

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

_session = requests.Session()


def _headers() -> dict:
    return {"User-Agent": random.choice(_UA), "Accept-Language": "en-US,en;q=0.9"}


def _get(url: str, **kwargs: Any) -> requests.Response:
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("headers", _headers())
    resp = _session.get(url, **kwargs)
    resp.raise_for_status()
    return resp


def _post_json(url: str, body: dict, **kwargs: Any) -> requests.Response:
    kwargs.setdefault("timeout", 30)
    kwargs.setdefault("headers", {**_headers(), "Content-Type": "application/json"})
    resp = _session.post(url, json=body, **kwargs)
    resp.raise_for_status()
    return resp


# ── Tier 1 : Open APIs ──────────────────────────────────────────────────────


def fetch_remotive() -> list[RawJob]:
    """https://remotive.com – free, no key."""
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:6]:
        try:
            data = _get(f"https://remotive.com/api/remote-jobs?search={quote_plus(term)}&limit=100").json()
            for item in data.get("jobs", []):
                jobs.append(RawJob(
                    source="remotive",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", ""),
                    description=item.get("description", ""),
                    apply_link=item.get("url", ""),
                    posted_at=item.get("publication_date", ""),
                    salary_text=item.get("salary", ""),
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("remotive (%s): %s", term, exc)
    return jobs


def fetch_remoteok() -> list[RawJob]:
    """https://remoteok.com – free JSON feed."""
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:6]:
        try:
            data = _get(
                f"https://remoteok.com/api?tag={quote_plus(term)}",
                headers={**_headers(), "Accept": "application/json"},
            ).json()
            for item in data:
                if not isinstance(item, dict) or "id" not in item:
                    continue
                jobs.append(RawJob(
                    source="remoteok",
                    external_id=str(item.get("id", "")),
                    title=item.get("position", ""),
                    company=item.get("company", ""),
                    location=item.get("location", "Worldwide"),
                    description=item.get("description", ""),
                    apply_link=item.get("url", item.get("apply_url", "")),
                    posted_at=item.get("date", ""),
                    salary_text=f"{item.get('salary_min', '')} - {item.get('salary_max', '')}".strip(" -"),
                ))
            time.sleep(1)
        except Exception as exc:
            log.warning("remoteok (%s): %s", term, exc)
    return jobs


def fetch_arbeitnow() -> list[RawJob]:
    """https://arbeitnow.com – free, paginated."""
    jobs: list[RawJob] = []
    for page in range(1, 4):
        try:
            data = _get(f"https://www.arbeitnow.com/api/job-board-api?page={page}").json()
            for item in data.get("data", []):
                jobs.append(RawJob(
                    source="arbeitnow",
                    external_id=str(item.get("slug", "")),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("location", ""),
                    description=item.get("description", ""),
                    apply_link=item.get("url", ""),
                    posted_at=item.get("created_at", ""),
                    salary_text="",
                ))
            if not data.get("data"):
                break
            time.sleep(0.5)
        except Exception as exc:
            log.warning("arbeitnow page %d: %s", page, exc)
            break
    return jobs


def fetch_himalayas() -> list[RawJob]:
    """https://himalayas.app – free, no key."""
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:6]:
        try:
            data = _get(
                f"https://himalayas.app/jobs/api",
                params={"limit": "50", "search": term},
            ).json()
            for item in data.get("jobs", []):
                jobs.append(RawJob(
                    source="himalayas",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    location=item.get("location", "Remote"),
                    description=item.get("description", ""),
                    apply_link=item.get("applicationLink", item.get("url", "")),
                    posted_at=item.get("pubDate", ""),
                    salary_text=f"{item.get('minSalary', '')} - {item.get('maxSalary', '')}".strip(" -"),
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("himalayas (%s): %s", term, exc)
    return jobs


def fetch_jobicy() -> list[RawJob]:
    """https://jobicy.com – free REST API."""
    jobs: list[RawJob] = []
    for tag in ["developer", "dotnet", "csharp", "angular", "backend"]:
        try:
            data = _get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"count": "50", "tag": tag},
            ).json()
            for item in data.get("jobs", []):
                jobs.append(RawJob(
                    source="jobicy",
                    external_id=str(item.get("id", "")),
                    title=item.get("jobTitle", ""),
                    company=item.get("companyName", ""),
                    location=item.get("jobGeo", "Remote"),
                    description=item.get("jobDescription", ""),
                    apply_link=item.get("url", ""),
                    posted_at=item.get("pubDate", ""),
                    salary_text=f"{item.get('annualSalaryMin', '')} - {item.get('annualSalaryMax', '')}".strip(" -"),
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("jobicy (%s): %s", tag, exc)
    return jobs


def fetch_themuse() -> list[RawJob]:
    """https://www.themuse.com – free public API."""
    jobs: list[RawJob] = []
    for level in ["Mid Level", "Senior Level"]:
        for page in range(0, 5):
            try:
                data = _get(
                    "https://www.themuse.com/api/public/jobs",
                    params={"category": "Software Engineering", "level": level, "page": str(page)},
                ).json()
                for item in data.get("results", []):
                    locs = ", ".join(loc.get("name", "") for loc in item.get("locations", []))
                    jobs.append(RawJob(
                        source="themuse",
                        external_id=str(item.get("id", "")),
                        title=item.get("name", ""),
                        company=item.get("company", {}).get("name", ""),
                        location=locs or "Flexible",
                        description=item.get("contents", ""),
                        apply_link=item.get("refs", {}).get("landing_page", ""),
                        posted_at=item.get("publication_date", ""),
                        salary_text="",
                    ))
                time.sleep(0.5)
            except Exception as exc:
                log.warning("themuse %s page %d: %s", level, page, exc)
                break
    return jobs


def fetch_findwork() -> list[RawJob]:
    """https://findwork.dev – REQUIRES API key now (was free).
    Register at https://findwork.dev to get a token."""
    token = os.getenv("FINDWORK_API_KEY", "").strip()
    if not token:
        return []
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:2]:
        try:
            data = _get(
                "https://findwork.dev/api/jobs/",
                params={"search": term, "remote": "true"},
                headers={**_headers(), "Authorization": f"Token {token}"},
            ).json()
            for item in data.get("results", []):
                jobs.append(RawJob(
                    source="findwork",
                    external_id=str(item.get("id", "")),
                    title=item.get("role", ""),
                    company=item.get("company_name", ""),
                    location=item.get("location", "Remote"),
                    description=item.get("text", ""),
                    apply_link=item.get("url", ""),
                    posted_at=item.get("date_posted", ""),
                    salary_text="",
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("findwork (%s): %s", term, exc)
    return jobs


def fetch_joboard() -> list[RawJob]:
    """joboard.io – domain is defunct, keeping stub for registry compat."""
    return []


def fetch_github_jobs() -> list[RawJob]:
    """GitHub Jobs via the official jobs page – free."""
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:3]:
        try:
            data = _get(
                "https://jobs.github.com/positions.json",
                params={"search": term, "location": "remote"},
            ).json()
            for item in data:
                if not isinstance(item, dict):
                    continue
                jobs.append(RawJob(
                    source="github_jobs",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", "Remote"),
                    description=item.get("description", ""),
                    apply_link=item.get("url", item.get("company_url", "")),
                    posted_at=item.get("created_at", ""),
                    salary_text="",
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("github_jobs (%s): %s", term, exc)
    return jobs


def fetch_whoishiring() -> list[RawJob]:
    """HackerNews Who Is Hiring threads – free via Algolia HN API."""
    jobs: list[RawJob] = []
    try:
        # Get the latest "Who is hiring" thread
        data = _get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"query": "\"Who is hiring\"", "tags": "story", "numericFilters": "points>100"},
        ).json()
        hits = data.get("hits", [])
        if not hits:
            return []
        story_id = hits[0].get("objectID", "")
        if not story_id:
            return []

        # Get comments from that thread
        comments = _get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": f"comment,story_{story_id}", "hitsPerPage": "200"},
        ).json()

        for item in comments.get("hits", []):
            text = item.get("comment_text", "")
            if not text:
                continue
            text_l = text.lower()
            # Only keep comments mentioning our skills
            if not any(kw in text_l for kw in [".net", "c#", "dotnet", "angular", "microservice"]):
                continue
            # Extract company name (usually first line / first few words)
            first_line = text.split("<p>")[0].split("|")[0].strip()
            from html import unescape
            first_line = unescape(re.sub(r"<[^>]+>", "", first_line))
            comment_id = item.get("objectID", "")
            jobs.append(RawJob(
                source="whoishiring",
                external_id=str(comment_id),
                title=".NET/C# Role (HN Who Is Hiring)",
                company=first_line[:80] if first_line else "See listing",
                location="Remote",
                description=unescape(re.sub(r"<[^>]+>", " ", text))[:2000],
                apply_link=f"https://news.ycombinator.com/item?id={comment_id}",
                posted_at=item.get("created_at", ""),
                salary_text="",
            ))
    except Exception as exc:
        log.warning("whoishiring: %s", exc)
    return jobs


# ── Tier 2 : Free key APIs ──────────────────────────────────────────────────


def fetch_adzuna(country: str = "in") -> list[RawJob]:
    """Adzuna – 200 free requests/day, covers IN/GB/US/AU/DE/AE and more."""
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        return []
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:4]:
        try:
            data = _get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": term,
                    "where": "remote",
                    "results_per_page": "50",
                    "content-type": "application/json",
                },
            ).json()
            for item in data.get("results", []):
                jobs.append(RawJob(
                    source=f"adzuna_{country}",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("company", {}).get("display_name", ""),
                    location=item.get("location", {}).get("display_name", ""),
                    description=item.get("description", ""),
                    apply_link=item.get("redirect_url", ""),
                    posted_at=item.get("created", ""),
                    salary_text=(
                        f"{item.get('salary_min', '')} - {item.get('salary_max', '')}"
                        if item.get("salary_min")
                        else ""
                    ),
                ))
            time.sleep(0.3)
        except Exception as exc:
            log.warning("adzuna_%s (%s): %s", country, term, exc)
    return jobs


ADZUNA_COUNTRIES = ["in", "gb", "us", "au", "de", "ca", "nl"]


def fetch_all_adzuna() -> list[RawJob]:
    jobs: list[RawJob] = []
    for country in ADZUNA_COUNTRIES:
        jobs.extend(fetch_adzuna(country))
    return jobs


def fetch_reed() -> list[RawJob]:
    """Reed.co.uk – free API key registration."""
    api_key = os.getenv("REED_API_KEY", "").strip()
    if not api_key:
        return []
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:2]:
        try:
            data = _get(
                "https://www.reed.co.uk/api/1.0/search",
                params={"keywords": term, "locationName": "remote", "resultsToTake": "50"},
                headers={**_headers()},
                auth=(api_key, ""),
            ).json()
            for item in data.get("results", []):
                jobs.append(RawJob(
                    source="reed",
                    external_id=str(item.get("jobId", "")),
                    title=item.get("jobTitle", ""),
                    company=item.get("employerName", ""),
                    location=item.get("locationName", ""),
                    description=item.get("jobDescription", ""),
                    apply_link=item.get("jobUrl", ""),
                    posted_at=item.get("date", ""),
                    salary_text=(
                        f"£{item.get('minimumSalary', '')} - £{item.get('maximumSalary', '')}"
                        if item.get("minimumSalary")
                        else ""
                    ),
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("reed (%s): %s", term, exc)
    return jobs


def fetch_jooble() -> list[RawJob]:
    """Jooble – free API key, POST-based."""
    api_key = os.getenv("JOOBLE_API_KEY", "").strip()
    if not api_key:
        return []
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:2]:
        try:
            data = _post_json(
                f"https://jooble.org/api/{api_key}",
                {"keywords": term, "location": "remote", "page": "1"},
            ).json()
            for item in data.get("jobs", []):
                jobs.append(RawJob(
                    source="jooble",
                    external_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    description=item.get("snippet", ""),
                    apply_link=item.get("link", ""),
                    posted_at=item.get("updated", ""),
                    salary_text=item.get("salary", ""),
                ))
            time.sleep(0.5)
        except Exception as exc:
            log.warning("jooble (%s): %s", term, exc)
    return jobs


# ── Master list ──────────────────────────────────────────────────────────────

OPEN_API_SOURCES = [
    ("remotive", fetch_remotive),
    ("remoteok", fetch_remoteok),
    ("arbeitnow", fetch_arbeitnow),
    ("himalayas", fetch_himalayas),
    ("jobicy", fetch_jobicy),
    ("themuse", fetch_themuse),
    ("whoishiring", fetch_whoishiring),
]

KEYED_API_SOURCES = [
    ("adzuna_multi", fetch_all_adzuna),
    ("reed", fetch_reed),
    ("jooble", fetch_jooble),
    ("findwork", fetch_findwork),
]

"""Master orchestrator – collects jobs from all API + scraping sources.

Sources (20+):
  API:  Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, The Muse,
        FindWork, JoBoard, Adzuna (9 countries), Reed, Jooble
  Scraping: LinkedIn, Indeed (9 countries), Shine.com, DuckDuckGo,
            Company Career Pages (Greenhouse/Lever boards)
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from app.models import RawJob
from app.sources.api_sources import KEYED_API_SOURCES, OPEN_API_SOURCES
from app.sources.scraper_sources import SCRAPER_SOURCES

log = logging.getLogger(__name__)


def _safe(fn: Callable[[], list[RawJob]], name: str) -> list[RawJob]:
    """Execute a source fetcher with error isolation."""
    try:
        jobs = fn()
        log.info("[%s] returned %d jobs", name, len(jobs))
        return jobs
    except Exception as exc:
        log.warning("[%s] FAILED: %s", name, exc)
        return []


def fetch_all_sources() -> list[RawJob]:
    """Fetch from every registered source, fail-safe per source."""
    all_jobs: list[RawJob] = []

    # Tier 1 – open APIs (most reliable)
    for name, fn in OPEN_API_SOURCES:
        all_jobs.extend(_safe(fn, name))
        time.sleep(0.3)

    # Tier 2 – keyed APIs (only if keys configured)
    for name, fn in KEYED_API_SOURCES:
        all_jobs.extend(_safe(fn, name))
        time.sleep(0.3)

    # Tier 3 – scrapers (may fail, that's OK)
    for name, fn in SCRAPER_SOURCES:
        all_jobs.extend(_safe(fn, name))
        time.sleep(0.5)

    log.info("Total raw jobs collected: %d", len(all_jobs))
    return all_jobs

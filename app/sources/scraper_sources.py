"""Web-scraping job sources for portals without free APIs.

Best-effort scrapers — these may break when portal HTML changes.
Each function is wrapped with error handling so pipeline always continues.

Covers:
    LinkedIn (public search), Naukri.com (API), Indeed (RSS multi-country),
    DuckDuckGo job search
"""
from __future__ import annotations

import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus, urlencode, urljoin

import requests
from bs4 import BeautifulSoup, Tag

from app.models import RawJob

log = logging.getLogger(__name__)

SEARCH_TERMS = [
    ".net developer remote",
    "c# developer remote",
    "angular developer remote",
    "dotnet developer remote",
    "asp.net developer remote",
    ".net core developer",
    "full stack .net",
    "azure .net developer",
    "microservices c# remote",
    "backend c# developer",
]

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

_session = requests.Session()


def _headers() -> dict:
    return {
        "User-Agent": random.choice(_UA),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _get_html(url: str, **kwargs: Any) -> BeautifulSoup:
    kwargs.setdefault("timeout", 20)
    hdr = _headers()
    hdr["Accept-Encoding"] = "gzip, deflate"
    hdr["Connection"] = "keep-alive"
    hdr["Upgrade-Insecure-Requests"] = "1"
    hdr["Cache-Control"] = "max-age=0"
    kwargs.setdefault("headers", hdr)
    kwargs.setdefault("allow_redirects", True)
    resp = _session.get(url, **kwargs)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def _text(tag: Tag | None) -> str:
    return tag.get_text(strip=True) if tag else ""


# ── LinkedIn (public search – no login) ─────────────────────────────────────


def fetch_linkedin() -> list[RawJob]:
    """Scrape LinkedIn public job search pages (first 25 results per query)."""
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:6]:
        try:
            params = {"keywords": term, "f_WT": "2", "position": "1", "pageNum": "0"}
            soup = _get_html("https://www.linkedin.com/jobs/search/?" + urlencode(params))
            cards = soup.select("div.base-card, li.result-card, div.job-search-card")
            for card in cards[:25]:
                title_el = card.select_one("h3.base-search-card__title, h3.result-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle, h4.result-card__subtitle")
                loc_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link, a.result-card__full-link")
                link = (link_el["href"] if link_el and link_el.get("href") else "").split("?")[0]
                if not _text(title_el) or not link:
                    continue
                jobs.append(RawJob(
                    source="linkedin",
                    external_id=link.rstrip("/").split("/")[-1] if "/" in link else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "Remote",
                    description="",
                    apply_link=link,
                    posted_at="",
                    salary_text="",
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("linkedin (%s): %s", term, exc)
    return jobs


# ── Naukri.com (API endpoint — much more reliable than HTML scrape) ──────────


_NAUKRI_API = "https://www.naukri.com/jobapi/v3/search"

_NAUKRI_QUERIES = [
    {"keyword": ".net developer", "location": "remote"},
    {"keyword": "c# developer", "location": "remote"},
    {"keyword": "dotnet developer", "location": ""},
    {"keyword": ".net core developer", "location": ""},
    {"keyword": "asp.net developer", "location": ""},
    {"keyword": "angular developer", "location": "remote"},
    {"keyword": "full stack .net", "location": ""},
    {"keyword": "microservices c#", "location": ""},
    {"keyword": ".net developer", "location": "pune"},
    {"keyword": ".net developer", "location": "bangalore"},
    {"keyword": ".net developer", "location": "hyderabad"},
    {"keyword": "c# developer", "location": "mumbai"},
]


def fetch_naukri() -> list[RawJob]:
    """Fetch jobs from Naukri.com using their internal search API.
    This returns JSON and is far more reliable than HTML scraping."""
    jobs: list[RawJob] = []
    seen_ids: set[str] = set()

    for q in _NAUKRI_QUERIES:
        try:
            params = {
                "noOfResults": 50,
                "urlType": "search_by_keyword",
                "searchType": "adv",
                "keyword": q["keyword"],
                "pageNo": 1,
                "k": q["keyword"],
                "suitableJobs": "false",
                "src": "jobsearchDesk",
                "latLong": "",
            }
            if q["location"]:
                params["location"] = q["location"]

            headers = {
                "User-Agent": random.choice(_UA),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
                "appid": "109",
                "systemid": "Naukri",
                "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
                "Content-Type": "application/json",
            }
            resp = _session.get(_NAUKRI_API, params=params, headers=headers, timeout=20)

            if resp.status_code == 200:
                data = resp.json()
                job_details = data.get("jobDetails", [])
                for item in job_details:
                    jid = str(item.get("jobId", ""))
                    if not jid or jid in seen_ids:
                        continue
                    seen_ids.add(jid)

                    title = item.get("title", "")
                    company = item.get("companyName", "")
                    apply_link = item.get("jdURL", "")
                    if apply_link and not apply_link.startswith("http"):
                        apply_link = "https://www.naukri.com" + apply_link

                    # Extract skills from tags
                    tags = item.get("tagsAndSkills", "") or ""
                    placeholders = item.get("placeholders", [])
                    location_parts = []
                    experience_text = ""
                    salary_text = ""
                    for ph in placeholders:
                        if ph.get("type") == "location":
                            location_parts.append(ph.get("label", ""))
                        elif ph.get("type") == "experience":
                            experience_text = ph.get("label", "")
                        elif ph.get("type") == "salary":
                            salary_text = ph.get("label", "")

                    location = ", ".join(location_parts) if location_parts else "India"
                    description = f"{tags} | Experience: {experience_text}" if experience_text else tags

                    if not title or not apply_link:
                        continue

                    jobs.append(RawJob(
                        source="naukri",
                        external_id=jid,
                        title=title,
                        company=company,
                        location=location,
                        description=description,
                        apply_link=apply_link,
                        posted_at=item.get("footerPlaceholderLabel", ""),
                        salary_text=salary_text,
                    ))
            else:
                log.warning("naukri API (%s): HTTP %d", q["keyword"], resp.status_code)

            time.sleep(1.5)
        except Exception as exc:
            log.warning("naukri (%s): %s", q["keyword"], exc)

    log.info("naukri API: fetched %d jobs across %d queries", len(jobs), len(_NAUKRI_QUERIES))
    return jobs


# ── Indeed (RSS feeds — multi-country, no JS needed) ─────────────────────────

INDEED_RSS_FEEDS = {
    "in": "https://www.indeed.co.in/rss",
    "us": "https://www.indeed.com/rss",
    "uk": "https://uk.indeed.com/rss",
    "au": "https://au.indeed.com/rss",
    "ca": "https://ca.indeed.com/rss",
    "ae": "https://www.indeed.ae/rss",
    "de": "https://de.indeed.com/rss",
    "sg": "https://www.indeed.com.sg/rss",
    "nl": "https://www.indeed.nl/rss",
}

_INDEED_TERMS = [
    ".net developer",
    "c# developer",
    "dotnet developer",
    ".net core",
    "angular developer",
]


def _fetch_indeed_rss(base_url: str, country: str) -> list[RawJob]:
    """Fetch jobs from Indeed RSS feed for one country."""
    jobs: list[RawJob] = []
    seen: set[str] = set()

    for term in _INDEED_TERMS:
        try:
            params = {"q": term, "l": "remote", "sort": "date", "fromage": "7"}
            # India-specific: search across multiple cities too
            locations = ["remote"]
            if country == "in":
                locations.extend(["work from home", "pune", "bangalore", "hyderabad"])

            for loc in locations:
                params["l"] = loc
                url = f"{base_url}?{urlencode(params)}"
                resp = _session.get(url, headers=_headers(), timeout=20)

                if resp.status_code != 200:
                    continue

                # Parse RSS XML
                try:
                    root = ET.fromstring(resp.text)
                except ET.ParseError:
                    continue

                for item in root.iter("item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")
                    pub_el = item.find("pubDate")
                    source_el = item.find("source")

                    title = title_el.text.strip() if title_el is not None and title_el.text else ""
                    link = link_el.text.strip() if link_el is not None and link_el.text else ""
                    desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                    pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
                    company = source_el.text.strip() if source_el is not None and source_el.text else ""

                    if not title or not link or link in seen:
                        continue
                    seen.add(link)

                    # Strip HTML from description
                    if "<" in desc:
                        desc = BeautifulSoup(desc, "lxml").get_text(strip=True)

                    jobs.append(RawJob(
                        source=f"indeed_{country}",
                        external_id=link.split("jk=")[-1][:16] if "jk=" in link else link[-20:],
                        title=title,
                        company=company,
                        location=f"Remote ({country.upper()})" if loc == "remote" else loc.title(),
                        description=desc[:500],
                        apply_link=link,
                        posted_at=pub_date,
                        salary_text="",
                    ))

                if country != "in":
                    break  # Only India gets multi-city search

            time.sleep(1)
        except Exception as exc:
            log.warning("indeed_rss_%s (%s): %s", country, term, exc)

    return jobs


def fetch_indeed_all() -> list[RawJob]:
    """Fetch from all Indeed RSS feeds across countries."""
    all_jobs: list[RawJob] = []
    for country, base_url in INDEED_RSS_FEEDS.items():
        try:
            result = _fetch_indeed_rss(base_url, country)
            all_jobs.extend(result)
            log.info("indeed_rss_%s: %d jobs", country, len(result))
        except Exception as exc:
            log.warning("indeed_rss_%s: %s", country, exc)
        time.sleep(0.5)
    return all_jobs


# ── Wellfound / AngelList ──────────────────────────────────────────────────


def fetch_wellfound() -> list[RawJob]:
    jobs: list[RawJob] = []
    try:
        soup = _get_html(
            "https://wellfound.com/role/r/software-engineer?remote=true"
        )
        cards = soup.select("div.styles_result__rPRSS, div[data-test='StartupResult']")
        for card in cards[:20]:
            title_el = card.select_one("a.styles_component__UCLp3, h4 a")
            company_el = card.select_one("h2 a, a.styles_component__UCLp3")
            loc_el = card.select_one("span.styles_location__ZnZMC")
            salary_el = card.select_one("span.styles_salary__il4cI")
            href = ""
            if title_el:
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://wellfound.com" + href
            if not _text(title_el):
                continue
            jobs.append(RawJob(
                source="wellfound",
                external_id=href.split("/")[-1] if href else "",
                title=_text(title_el),
                company=_text(company_el),
                location=_text(loc_el) or "Remote",
                description="",
                apply_link=href or "https://wellfound.com",
                posted_at="",
                salary_text=_text(salary_el),
            ))
    except Exception as exc:
        log.warning("wellfound: %s", exc)
    return jobs


# ── Glassdoor (public search) ──────────────────────────────────────────────


def fetch_glassdoor() -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in [".net developer", "angular developer"]:
        try:
            soup = _get_html(
                f"https://www.glassdoor.com/Job/remote-{quote_plus(term)}-jobs-SRCH_IL.0,6_IS11047_KO7,23.htm"
            )
            cards = soup.select("li.react-job-listing, li[data-test='jobListing']")
            for card in cards[:15]:
                title_el = card.select_one("a[data-test='job-link'], a.job-title")
                company_el = card.select_one("div.job-search-key-1, span.EmployerProfile_compactEmployerName__LE242")
                loc_el = card.select_one("span[data-test='emp-location']")
                salary_el = card.select_one("span[data-test='detailSalary']")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.glassdoor.com" + href
                if not _text(title_el):
                    continue
                jobs.append(RawJob(
                    source="glassdoor",
                    external_id=href.split("/")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "Remote",
                    description="",
                    apply_link=href or "https://www.glassdoor.com",
                    posted_at="",
                    salary_text=_text(salary_el),
                ))
            time.sleep(3)
        except Exception as exc:
            log.warning("glassdoor (%s): %s", term, exc)
    return jobs


# ── DuckDuckGo job search (backup aggregator) ──────────────────────────────


def fetch_duckduckgo_jobs() -> list[RawJob]:
    """Search DuckDuckGo for remote .NET jobs and extract job portal links."""
    jobs: list[RawJob] = []
    ddg_queries = [
        '"remote" ".net developer" site:linkedin.com/jobs OR site:indeed.com',
        '"remote" "c# developer" apply',
        '"remote" "angular developer" hiring',
    ]
    for query in ddg_queries:
        try:
            soup = _get_html(
                f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            )
            results = soup.select("div.result, div.result__body")
            for r in results[:10]:
                link_el = r.select_one("a.result__a, a.result__url")
                snippet_el = r.select_one("a.result__snippet, div.result__snippet")
                href = link_el.get("href", "") if link_el else ""
                title = _text(link_el)
                if not title or not href:
                    continue
                jobs.append(RawJob(
                    source="duckduckgo",
                    external_id=href[:64],
                    title=title,
                    company="",
                    location="Remote",
                    description=_text(snippet_el),
                    apply_link=href,
                    posted_at="",
                    salary_text="",
                ))
            time.sleep(3)
        except Exception as exc:
            log.warning("duckduckgo (%s): %s", query[:30], exc)
    return jobs


# ── Exports ──────────────────────────────────────────────────────────────────
# Active sources: LinkedIn, Naukri (API), Indeed (RSS multi-country), DuckDuckGo
# Dead (403): SimplyHired, GulfTalent, Bayt, CWJobs, Wellfound, Glassdoor

SCRAPER_SOURCES = [
    ("linkedin", fetch_linkedin),
    ("naukri", fetch_naukri),
    ("indeed_rss", fetch_indeed_all),
    ("duckduckgo", fetch_duckduckgo_jobs),
]

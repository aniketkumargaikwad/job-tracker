"""Web-scraping job sources for portals without free APIs.

Best-effort scrapers — these may break when portal HTML changes.
Each function is wrapped with error handling so pipeline always continues.

Covers:
    LinkedIn (public search), Shine.com (India), Indeed (RSS multi-country),
    DuckDuckGo job search, Company Career Pages (Greenhouse/Lever)
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

import app.sources as _sources_pkg
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


# ── Shine.com (Indian job portal — server-side rendered) ─────────────────────
# Naukri.com blocks server-side scraping with reCAPTCHA.
# Shine.com (by HT Media) is a reliable Indian alternative with SSR HTML.

_SHINE_SLUGS = [
    "dotnet-developer-work-from-home-jobs",
    "dot-net-developer-work-from-home-jobs",
    "c-sharp-developer-work-from-home-jobs",
    "asp-dot-net-developer-work-from-home-jobs",
    "angular-developer-work-from-home-jobs",
    "full-stack-dot-net-developer-work-from-home-jobs",
    "azure-developer-work-from-home-jobs",
    "dot-net-core-developer-work-from-home-jobs",
    "microservices-developer-work-from-home-jobs",
]


def fetch_shine() -> list[RawJob]:
    """Scrape Shine.com job search pages (server-side rendered HTML)."""
    jobs: list[RawJob] = []
    seen_urls: set[str] = set()

    for slug in _SHINE_SLUGS:
        try:
            url = f"https://www.shine.com/job-search/{slug}"
            resp = _session.get(url, headers=_headers(), timeout=20)
            if resp.status_code != 200:
                log.warning("shine (%s): HTTP %d", slug, resp.status_code)
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("div.jdbigCard")

            for card in cards:
                # URL from meta or title link
                meta_url = card.select_one('meta[itemprop="url"]')
                title_link = card.select_one("h3 a[href]")
                job_url = ""
                if meta_url and meta_url.get("content"):
                    job_url = meta_url["content"]
                elif title_link:
                    job_url = title_link.get("href", "")
                    if job_url and not job_url.startswith("http"):
                        job_url = "https://www.shine.com" + job_url

                if not job_url or job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # Title
                title_el = card.select_one("h3[itemprop='name'] a, h3 a")
                title = _text(title_el)
                if not title:
                    continue

                # Company
                company_el = card.select_one(
                    "span.jdTruncationCompany, "
                    "span[class*='bigCardTopTitleName']"
                )
                company = _text(company_el)

                # Location
                loc_el = card.select_one(
                    "div[class*='bigCardLocation'] span, "
                    "div[class*='bigCardCenterListLoc'] span"
                )
                location = _text(loc_el) or "India"

                # Experience
                exp_el = card.select_one(
                    "span[class*='bigCardCenterListExp'], "
                    "div[class*='bigCardExperience'] span"
                )

                # Skills
                skill_els = card.select("div.jdSkills li")
                skills = ", ".join(_text(s) for s in skill_els if _text(s))

                # Posted date
                posted_el = card.select_one("span[class*='postedData']")
                posted = _text(posted_el) if posted_el else ""

                # External ID from URL path
                eid = job_url.rstrip("/").split("/")[-1]

                jobs.append(RawJob(
                    source="shine",
                    external_id=eid,
                    title=title,
                    company=company,
                    location=location,
                    description=skills,
                    apply_link=job_url,
                    posted_at=posted,
                    salary_text="",
                    experience=_text(exp_el) if exp_el else "",
                ))

            time.sleep(1.5)
        except Exception as exc:
            log.warning("shine (%s): %s", slug, exc)

    log.info("shine: fetched %d jobs across %d slugs", len(jobs), len(_SHINE_SLUGS))
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
            params = {"q": term, "l": "remote", "sort": "date", "fromage": str(_sources_pkg._lookback_days)}
            # Only search remote positions across all countries
            locations = ["remote"]

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
                        location=f"Remote ({country.upper()})",
                        description=desc[:500],
                        apply_link=link,
                        posted_at=pub_date,
                        salary_text="",
                    ))

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


# ── Company Career Pages (Google/DuckDuckGo discovery) ─────────────────────

# Well-known company career API endpoints and Greenhouse/Lever/Workday boards
# that expose JSON job listings. Each entry: (company_name, jobs_url, parser_type)
_CAREER_BOARDS = [
    # ── Greenhouse boards (JSON API) ──
    ("Microsoft", "https://boards-api.greenhouse.io/v1/boards/microsoftit/jobs", "greenhouse"),
    ("Twilio", "https://boards-api.greenhouse.io/v1/boards/twilio/jobs", "greenhouse"),
    ("GitLab", "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs", "greenhouse"),
    ("Cloudflare", "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs", "greenhouse"),
    ("Elastic", "https://boards-api.greenhouse.io/v1/boards/elastic/jobs", "greenhouse"),
    ("HashiCorp", "https://boards-api.greenhouse.io/v1/boards/hashicorp/jobs", "greenhouse"),
    ("Figma", "https://boards-api.greenhouse.io/v1/boards/figma/jobs", "greenhouse"),
    ("DataDog", "https://boards-api.greenhouse.io/v1/boards/datadog/jobs", "greenhouse"),
    ("Confluent", "https://boards-api.greenhouse.io/v1/boards/confluent/jobs", "greenhouse"),
    ("MongoDB", "https://boards-api.greenhouse.io/v1/boards/mongodb/jobs", "greenhouse"),
    ("PagerDuty", "https://boards-api.greenhouse.io/v1/boards/pagerduty/jobs", "greenhouse"),
    ("Reddit", "https://boards-api.greenhouse.io/v1/boards/reddit/jobs", "greenhouse"),
    ("Coinbase", "https://boards-api.greenhouse.io/v1/boards/coinbase/jobs", "greenhouse"),
    ("Amplitude", "https://boards-api.greenhouse.io/v1/boards/amplitude/jobs", "greenhouse"),
    ("Notion", "https://boards-api.greenhouse.io/v1/boards/notion/jobs", "greenhouse"),
    ("Samsara", "https://boards-api.greenhouse.io/v1/boards/samsara/jobs", "greenhouse"),
    ("Toast", "https://boards-api.greenhouse.io/v1/boards/toast/jobs", "greenhouse"),
    ("Grafana Labs", "https://boards-api.greenhouse.io/v1/boards/grafanalabs/jobs", "greenhouse"),
    ("Navan", "https://boards-api.greenhouse.io/v1/boards/navan/jobs", "greenhouse"),
    ("Airtable", "https://boards-api.greenhouse.io/v1/boards/airtable/jobs", "greenhouse"),
    ("Brex", "https://boards-api.greenhouse.io/v1/boards/brex/jobs", "greenhouse"),
    ("Plaid", "https://boards-api.greenhouse.io/v1/boards/plaid/jobs", "greenhouse"),
    ("Snyk", "https://boards-api.greenhouse.io/v1/boards/snyk/jobs", "greenhouse"),
    ("CrowdStrike", "https://boards-api.greenhouse.io/v1/boards/crowdstrike/jobs", "greenhouse"),
    ("Okta", "https://boards-api.greenhouse.io/v1/boards/okta/jobs", "greenhouse"),
    ("Gusto", "https://boards-api.greenhouse.io/v1/boards/gusto/jobs", "greenhouse"),
    ("Compass", "https://boards-api.greenhouse.io/v1/boards/compass/jobs", "greenhouse"),
    ("Drata", "https://boards-api.greenhouse.io/v1/boards/drata/jobs", "greenhouse"),
    ("CircleCI", "https://boards-api.greenhouse.io/v1/boards/circleci/jobs", "greenhouse"),
    ("Sourcegraph", "https://boards-api.greenhouse.io/v1/boards/sourcegraph/jobs", "greenhouse"),
    ("Temporal", "https://boards-api.greenhouse.io/v1/boards/temporal/jobs", "greenhouse"),
    ("LaunchDarkly", "https://boards-api.greenhouse.io/v1/boards/launchdarkly/jobs", "greenhouse"),
    # ── Lever boards (JSON API) ──
    ("Netflix", "https://jobs.lever.co/v0/postings/netflix?mode=json", "lever"),
    ("Spotify", "https://jobs.lever.co/v0/postings/spotify?mode=json", "lever"),
    ("Shopify", "https://jobs.lever.co/v0/postings/shopify?mode=json", "lever"),
    ("Stripe", "https://jobs.lever.co/v0/postings/stripe?mode=json", "lever"),
    ("Atlassian", "https://jobs.lever.co/v0/postings/atlassian?mode=json", "lever"),
    ("Grab", "https://jobs.lever.co/v0/postings/grab?mode=json", "lever"),
    ("Affirm", "https://jobs.lever.co/v0/postings/affirm?mode=json", "lever"),
    ("Vercel", "https://jobs.lever.co/v0/postings/vercel?mode=json", "lever"),
    ("Neon", "https://jobs.lever.co/v0/postings/neondatabase?mode=json", "lever"),
    ("Linear", "https://jobs.lever.co/v0/postings/linear?mode=json", "lever"),
    ("Postman", "https://jobs.lever.co/v0/postings/postman?mode=json", "lever"),
    ("Webflow", "https://jobs.lever.co/v0/postings/webflow?mode=json", "lever"),
]

# Skills to match in career-page job titles/descriptions
_CAREER_SKILL_PATTERN = re.compile(
    r"\.net|c#|dotnet|asp\.net|angular|blazor|entity\s*framework|azure.*developer|microservices",
    re.I,
)

_REMOTE_PATTERN = re.compile(
    r"remote|work\s*from\s*home|wfh|distributed|telecommute|anywhere",
    re.I,
)


def _parse_greenhouse(company: str, data: dict) -> list[RawJob]:
    """Parse Greenhouse board API response."""
    jobs: list[RawJob] = []
    for item in data.get("jobs", []):
        title = item.get("title", "")
        location = item.get("location", {}).get("name", "")
        combined = f"{title} {location}"
        # Must be remote AND match skills
        if not _REMOTE_PATTERN.search(combined):
            continue
        if not _CAREER_SKILL_PATTERN.search(combined):
            # Also check departments/metadata
            dept_text = " ".join(
                d.get("name", "") for d in item.get("departments", [])
            )
            if not _CAREER_SKILL_PATTERN.search(dept_text):
                continue
        abs_url = item.get("absolute_url", "")
        jobs.append(RawJob(
            source="career_page",
            external_id=str(item.get("id", "")),
            title=title,
            company=company,
            location=location or "Remote",
            description=BeautifulSoup(
                item.get("content", "")[:1000], "lxml"
            ).get_text(strip=True) if item.get("content") else "",
            apply_link=abs_url,
            posted_at=item.get("updated_at", "")[:10],
            salary_text="",
        ))
    return jobs


def _parse_lever(company: str, data: list) -> list[RawJob]:
    """Parse Lever board API response."""
    jobs: list[RawJob] = []
    if not isinstance(data, list):
        return jobs
    for item in data:
        title = item.get("text", "")
        cats = item.get("categories", {})
        location = cats.get("location", "")
        commitment = cats.get("commitment", "")
        combined = f"{title} {location} {commitment}"
        # Must be remote AND match skills
        if not _REMOTE_PATTERN.search(combined):
            continue
        if not _CAREER_SKILL_PATTERN.search(combined):
            desc_plain = item.get("descriptionPlain", "")[:500]
            if not _CAREER_SKILL_PATTERN.search(desc_plain):
                continue
        jobs.append(RawJob(
            source="career_page",
            external_id=item.get("id", ""),
            title=title,
            company=company,
            location=location or "Remote",
            description=item.get("descriptionPlain", "")[:500],
            apply_link=item.get("hostedUrl", item.get("applyUrl", "")),
            posted_at=str(item.get("createdAt", ""))[:10],
            salary_text="",
        ))
    return jobs


def fetch_career_pages() -> list[RawJob]:
    """Scrape remote .NET/C#/Angular jobs from company career pages.

    Uses Greenhouse & Lever public JSON APIs — no auth needed.
    Only keeps jobs that are explicitly remote AND match target skills.
    """
    all_jobs: list[RawJob] = []
    for company, url, parser_type in _CAREER_BOARDS:
        try:
            resp = _session.get(url, headers=_headers(), timeout=20)
            if resp.status_code != 200:
                log.debug("career_page %s: HTTP %d", company, resp.status_code)
                continue
            data = resp.json()
            if parser_type == "greenhouse":
                jobs = _parse_greenhouse(company, data)
            elif parser_type == "lever":
                jobs = _parse_lever(company, data)
            else:
                continue
            if jobs:
                log.info("career_page %s: %d remote jobs found", company, len(jobs))
            all_jobs.extend(jobs)
            time.sleep(0.5)
        except Exception as exc:
            log.debug("career_page %s: %s", company, exc)
    log.info("career_pages: total %d jobs from %d company boards", len(all_jobs), len(_CAREER_BOARDS))
    return all_jobs


# ── Exports ──────────────────────────────────────────────────────────────────
# Active sources: LinkedIn, Shine.com (India), Indeed (RSS multi-country),
#                 DuckDuckGo, Company Career Pages (Greenhouse/Lever)

SCRAPER_SOURCES = [
    ("linkedin", fetch_linkedin),
    ("shine", fetch_shine),
    ("indeed_rss", fetch_indeed_all),
    ("duckduckgo", fetch_duckduckgo_jobs),
    ("career_pages", fetch_career_pages),
]

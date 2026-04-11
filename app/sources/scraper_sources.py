"""Web-scraping job sources for portals without free APIs.

Best-effort scrapers — these may break when portal HTML changes.
Each function is wrapped with error handling so pipeline always continues.

Covers:
    LinkedIn (public search), Indeed (IN/US/UK/AU/AE/EU), Naukri.com,
    SimplyHired, GulfTalent, Bayt.com, CWJobs, Wellfound (AngelList),
    Glassdoor public, Google Jobs via DuckDuckGo
"""
from __future__ import annotations

import logging
import random
import re
import time
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


# ── Indeed (multi-country) ──────────────────────────────────────────────────

INDEED_DOMAINS = {
    "in": "https://www.indeed.co.in",
    "us": "https://www.indeed.com",
    "uk": "https://www.indeed.co.uk",
    "au": "https://au.indeed.com",
    "ae": "https://www.indeed.ae",
    "ca": "https://ca.indeed.com",
    "de": "https://de.indeed.com",
    "nl": "https://www.indeed.nl",
    "sg": "https://www.indeed.com.sg",
}


def _fetch_indeed_country(domain: str, country: str) -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:2]:
        try:
            params = {"q": term, "l": "", "remotejob": "032b3046-06a3-4876-8dfd-474eb5e7ed11", "sort": "date", "fromage": "7"}
            soup = _get_html(f"{domain}/jobs?" + urlencode(params))
            cards = soup.select("div.job_seen_beacon, div.cardOutline, div.result")
            for card in cards[:20]:
                title_el = card.select_one("h2.jobTitle a, a.jcs-JobTitle")
                company_el = card.select_one("span[data-testid='company-name'], span.companyName")
                loc_el = card.select_one("div[data-testid='text-location'], div.companyLocation")
                salary_el = card.select_one("div.salary-snippet-container, div.metadata.salary-snippet-container")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = urljoin(domain, href)
                if not _text(title_el) or not href:
                    continue
                jobs.append(RawJob(
                    source=f"indeed_{country}",
                    external_id=href.split("jk=")[-1][:16] if "jk=" in href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "Remote",
                    description="",
                    apply_link=href,
                    posted_at="",
                    salary_text=_text(salary_el),
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("indeed_%s (%s): %s", country, term, exc)
    return jobs


def fetch_indeed_all() -> list[RawJob]:
    jobs: list[RawJob] = []
    for country, domain in INDEED_DOMAINS.items():
        result = _fetch_indeed_country(domain, country)
        jobs.extend(result)
        if not result:
            # If the first country fails with 403, skip remaining to save time
            log.info("Indeed %s returned 0 — continuing to next country", country)
    return jobs


# ── Naukri.com ──────────────────────────────────────────────────────────────


def fetch_naukri() -> list[RawJob]:
    """Scrape Naukri.com search results via their search URL format."""
    jobs: list[RawJob] = []
    queries = [
        "dot-net-developer-work-from-home",
        "c-sharp-developer-remote",
        "angular-developer-remote",
        "microservices-developer-remote",
    ]
    for q in queries:
        try:
            url = f"https://www.naukri.com/{q}-jobs"
            soup = _get_html(url)
            # Naukri uses multiple card formats
            cards = soup.select(
                "article.jobTuple, "
                "div.srp-jobtuple-wrapper, "
                "div.cust-job-tuple, "
                "div[class*='jobTuple'], "
                "div[class*='job-listing']"
            )
            for card in cards[:20]:
                title_el = card.select_one(
                    "a.title, a.job-title-href, "
                    "a[class*='title'], "
                    "h2 a"
                )
                company_el = card.select_one(
                    "a.subTitle, a.comp-name, "
                    "span.comp-name, "
                    "a[class*='comp-name'], "
                    "span[class*='comp-name']"
                )
                loc_el = card.select_one(
                    "span.locWdth, span.loc-wrap, "
                    "li.location span, span.loc, "
                    "span[class*='loc']"
                )
                salary_el = card.select_one(
                    "span.sal, li.salary span, "
                    "span.sal-wrap, "
                    "span[class*='sal']"
                )
                skills_el = card.select("li.tag, span.tag, span[class*='tag']")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                if not _text(title_el) or not href:
                    continue
                desc_parts = [_text(s) for s in skills_el]
                jobs.append(RawJob(
                    source="naukri",
                    external_id=href.split("-")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "India",
                    description=" ".join(desc_parts),
                    apply_link=href,
                    posted_at="",
                    salary_text=_text(salary_el),
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("naukri (%s): %s", q, exc)
    return jobs


# ── SimplyHired ─────────────────────────────────────────────────────────────


def fetch_simplyhired() -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in SEARCH_TERMS[:2]:
        try:
            soup = _get_html(
                f"https://www.simplyhired.com/search?q={quote_plus(term)}&l=remote"
            )
            cards = soup.select("article[data-testid='searchSerpJob'], li.SerpJob-jobCard")
            for card in cards[:20]:
                title_el = card.select_one("h2 a, a.card-link")
                company_el = card.select_one("span[data-testid='companyName'], span.JobPosting-labelWithIcon")
                loc_el = card.select_one("span[data-testid='searchSerpJobLocation']")
                salary_el = card.select_one("span[data-testid='searchSerpJobSalary']")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.simplyhired.com" + href
                if not _text(title_el) or not href:
                    continue
                jobs.append(RawJob(
                    source="simplyhired",
                    external_id=href.split("/")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "Remote",
                    description="",
                    apply_link=href,
                    posted_at="",
                    salary_text=_text(salary_el),
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("simplyhired (%s): %s", term, exc)
    return jobs


# ── GulfTalent (UAE / Middle East) ──────────────────────────────────────────


def fetch_gulftalet() -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in [".net", "angular"]:
        try:
            soup = _get_html(
                f"https://www.gulftalent.com/jobs/search?keywords={quote_plus(term)}&work_type=remote"
            )
            cards = soup.select("div.job-card, div.search-result, article.job-listing")
            for card in cards[:20]:
                title_el = card.select_one("h2 a, a.job-title")
                company_el = card.select_one("span.company-name, div.company")
                loc_el = card.select_one("span.location, div.location")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.gulftalent.com" + href
                if not _text(title_el):
                    continue
                jobs.append(RawJob(
                    source="gulftalet",
                    external_id=href.split("/")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "UAE",
                    description="",
                    apply_link=href or f"https://www.gulftalent.com/jobs/search?keywords={quote_plus(term)}",
                    posted_at="",
                    salary_text="",
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("gulftalet (%s): %s", term, exc)
    return jobs


# ── Bayt.com (Middle East) ──────────────────────────────────────────────────


def fetch_bayt() -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in [".net developer", "angular developer"]:
        try:
            soup = _get_html(
                f"https://www.bayt.com/en/international/jobs/{quote_plus(term)}-jobs/?filters%5Bjb_work_type_val%5D%5B%5D=remote"
            )
            cards = soup.select("li[data-js-job], div.has-new-job-card")
            for card in cards[:20]:
                title_el = card.select_one("h2 a, a.jb-title")
                company_el = card.select_one("b.jb-company, span.jb-company")
                loc_el = card.select_one("span.jb-loc")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.bayt.com" + href
                if not _text(title_el):
                    continue
                jobs.append(RawJob(
                    source="bayt",
                    external_id=href.split("/")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "Middle East",
                    description="",
                    apply_link=href or "https://www.bayt.com",
                    posted_at="",
                    salary_text="",
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("bayt (%s): %s", term, exc)
    return jobs


# ── CWJobs (UK) ────────────────────────────────────────────────────────────


def fetch_cwjobs() -> list[RawJob]:
    jobs: list[RawJob] = []
    for term in [".net", "c# developer"]:
        try:
            soup = _get_html(
                f"https://www.cwjobs.co.uk/jobs/{quote_plus(term)}/remote"
            )
            cards = soup.select("article[data-testid='job-card'], div.job-resultContent")
            for card in cards[:20]:
                title_el = card.select_one("h2 a, a[data-testid='job-title']")
                company_el = card.select_one("span[data-testid='company'], span.company")
                loc_el = card.select_one("span[data-testid='location']")
                salary_el = card.select_one("span[data-testid='salary']")
                href = ""
                if title_el:
                    href = title_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://www.cwjobs.co.uk" + href
                if not _text(title_el):
                    continue
                jobs.append(RawJob(
                    source="cwjobs",
                    external_id=href.split("/")[-1] if href else "",
                    title=_text(title_el),
                    company=_text(company_el),
                    location=_text(loc_el) or "UK Remote",
                    description="",
                    apply_link=href or "https://www.cwjobs.co.uk",
                    posted_at="",
                    salary_text=_text(salary_el),
                ))
            time.sleep(2)
        except Exception as exc:
            log.warning("cwjobs (%s): %s", term, exc)
    return jobs


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
# Only sources that actually work with plain requests are enabled.
# Indeed/SimplyHired/GulfTalent/Bayt/CWJobs/Wellfound/Glassdoor all return
# 403 Forbidden — they require browser JS rendering or CAPTCHA solving.
# Those are kept as functions above but excluded from the active list.

SCRAPER_SOURCES = [
    ("linkedin", fetch_linkedin),
    ("naukri", fetch_naukri),
    ("duckduckgo", fetch_duckduckgo_jobs),
]

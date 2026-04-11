"""Job enrichment – adds company info, salary estimation, skills, location data.

Salary strategy (tiered):
  1. Direct salary from description text
  2. Regex extraction for common formats (INR/USD/GBP/AED/EUR)
  3. Web-based salary research via DuckDuckGo (best effort)
  4. Heuristic estimate based on role level + company type + region
"""
from __future__ import annotations

import logging
import random
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from app.models import EnrichedJob, RawJob
from app.scoring import extract_skills, fingerprint, normalize_text, relevance_score

log = logging.getLogger(__name__)

# ── Known companies database ────────────────────────────────────────────────

KNOWN_MNC = {
    "microsoft", "amazon", "google", "accenture", "ibm", "oracle", "deloitte",
    "infosys", "tcs", "wipro", "cognizant", "hcl", "tech mahindra", "capgemini",
    "atos", "dxc technology", "ntt data", "fujitsu", "hitachi", "samsung",
    "intel", "cisco", "hp", "dell", "lenovo", "vmware", "sap", "ericsson",
    "nokia", "siemens", "bosch", "continental", "thales", "bae systems",
    "lockheed martin", "raytheon", "honeywell", "ge", "schneider electric",
    "philips", "lg", "sony", "panasonic", "huawei", "zte",
    "jpmorgan", "goldman sachs", "morgan stanley", "barclays", "hsbc",
    "citibank", "deutsche bank", "ubs", "credit suisse", "bnp paribas",
    "pwc", "ey", "kpmg", "mckinsey", "bain", "bcg",
    "unilever", "nestle", "procter & gamble", "johnson & johnson",
    "pfizer", "novartis", "roche", "astrazeneca", "merck",
    "shell", "bp", "total", "chevron", "exxon",
    "airbus", "boeing", "rolls-royce",
    "publicis sapient", "thoughtworks", "epam", "globant", "endava",
    "persistent systems", "ltimindtree", "mphasis", "hexaware", "cyient",
    "mindtree", "birlasoft", "zensar technologies", "coforge", "nagarro",
}

KNOWN_PRODUCT = {
    "microsoft", "google", "atlassian", "salesforce", "zoho", "adobe",
    "netflix", "spotify", "uber", "airbnb", "stripe", "shopify",
    "slack", "twilio", "datadog", "snowflake", "hashicorp", "confluent",
    "elastic", "mongodb", "redis labs", "cockroach labs", "planetscale",
    "figma", "canva", "notion", "miro", "airtable", "asana",
    "github", "gitlab", "jetbrains", "postman", "vercel", "netlify",
    "docker", "vmware", "nutanix", "palo alto networks", "crowdstrike",
    "zscaler", "okta", "auth0", "cloudflare",
    "freshworks", "chargebee", "razorpay", "zerodha", "dream11",
    "swiggy", "zomato", "flipkart", "meesho", "cred", "groww",
    "phonepe", "paytm", "ola", "urban company", "dunzo",
    "browserstack", "postman", "hasura", "innovaccer", "darwinbox",
    "druva", "icertis", "yellow.ai", "leadsquared",
    "sap", "oracle", "ibm", "intel", "cisco", "qualcomm", "nvidia",
    "paypal", "intuit", "servicenow", "workday", "veeva systems",
}

INDIAN_CITIES = [
    "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai",
    "gurugram", "gurgaon", "noida", "delhi", "new delhi", "kolkata",
    "ahmedabad", "jaipur", "thiruvananthapuram", "trivandrum", "kochi",
    "coimbatore", "indore", "chandigarh", "lucknow", "nagpur",
    "visakhapatnam", "vizag", "bhubaneswar", "mangalore", "mysore",
]

# ── Salary patterns ─────────────────────────────────────────────────────────

_SALARY_PATTERNS = [
    # INR formats
    re.compile(r"(?:inr|₹|rs\.?)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:-|to)\s*(?:inr|₹|rs\.?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|per annum|p\.?a\.?|/year|/yr)", re.I),
    re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:-|to)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?)", re.I),
    # USD formats
    re.compile(r"(?:usd|\$)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:-|to)\s*(?:usd|\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:per year|/year|/yr|p\.?a\.?|annually|k)", re.I),
    re.compile(r"(\d[\d,]*)\s*k?\s*(?:-|to)\s*(\d[\d,]*)\s*k\s*(?:usd|\$|per year|/year|annually)", re.I),
    # GBP
    re.compile(r"(?:gbp|£)\s*(\d[\d,]*)\s*(?:-|to)\s*(?:gbp|£)?\s*(\d[\d,]*)\s*(?:per annum|/year|p\.?a\.?|annually)?", re.I),
    # AED
    re.compile(r"(?:aed)\s*(\d[\d,]*)\s*(?:-|to)\s*(?:aed)?\s*(\d[\d,]*)\s*(?:per month|/month|monthly)?", re.I),
    # EUR
    re.compile(r"(?:eur|€)\s*(\d[\d,]*)\s*(?:-|to)\s*(?:eur|€)?\s*(\d[\d,]*)\s*(?:per year|/year|p\.?a\.?|annually)?", re.I),
    # Generic range with currency indicator
    re.compile(r"salary[:\s]*(\d[\d,]*)\s*(?:-|to)\s*(\d[\d,]*)", re.I),
]


def _extract_salary_from_text(text: str) -> str:
    """Try regex patterns against description to find salary."""
    for pattern in _SALARY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return ""


# ── Salary research via web search ──────────────────────────────────────────

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15",
]


def _research_salary(company: str, title: str) -> str:
    """Best-effort salary lookup via DuckDuckGo search."""
    if not company or not title:
        return ""
    try:
        query = f"{company} {title} salary glassdoor OR ambitionbox OR levels.fyi"
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers={"User-Agent": random.choice(_UA)},
            timeout=15,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        snippets = soup.select("a.result__snippet, div.result__snippet")
        for s in snippets[:5]:
            text = s.get_text(strip=True)
            found = _extract_salary_from_text(text)
            if found:
                return f"{found} (web research)"
    except Exception:
        pass
    return ""


def _heuristic_salary(title: str, company: str, location: str) -> str:
    """Fallback salary estimate based on role/company/location heuristics."""
    title_l = title.lower()
    company_l = company.lower()
    loc_l = location.lower()

    # Determine seniority
    if any(w in title_l for w in ("senior", "sr.", "lead", "principal", "staff", "architect")):
        level = "senior"
    elif any(w in title_l for w in ("junior", "jr.", "associate", "entry")):
        level = "junior"
    else:
        level = "mid"

    is_mnc = company_l in KNOWN_MNC
    is_product = company_l in KNOWN_PRODUCT

    # Determine region
    if any(w in loc_l for w in ("india", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon")):
        region = "india"
    elif any(w in loc_l for w in ("uae", "dubai", "abu dhabi", "qatar", "saudi")):
        region = "gulf"
    elif any(w in loc_l for w in ("uk", "london", "united kingdom", "england")):
        region = "uk"
    elif any(w in loc_l for w in ("us", "usa", "united states", "america", "new york", "california")):
        region = "us"
    elif any(w in loc_l for w in ("australia", "sydney", "melbourne")):
        region = "au"
    elif any(w in loc_l for w in ("europe", "germany", "netherlands", "france", "berlin", "amsterdam")):
        region = "eu"
    else:
        region = "global"

    # Salary estimation table (annual, approximate)
    salary_table = {
        ("junior", "india"):  "₹5-10 LPA",
        ("mid", "india"):     "₹12-22 LPA",
        ("senior", "india"):  "₹22-45 LPA",
        ("junior", "us"):     "$60K-90K",
        ("mid", "us"):        "$90K-140K",
        ("senior", "us"):     "$140K-220K",
        ("junior", "uk"):     "£30K-45K",
        ("mid", "uk"):        "£50K-80K",
        ("senior", "uk"):     "£80K-130K",
        ("junior", "gulf"):   "AED 8K-15K/mo",
        ("mid", "gulf"):      "AED 15K-30K/mo",
        ("senior", "gulf"):   "AED 30K-50K/mo",
        ("junior", "eu"):     "€35K-55K",
        ("mid", "eu"):        "€55K-85K",
        ("senior", "eu"):     "€85K-130K",
        ("junior", "au"):     "A$60K-90K",
        ("mid", "au"):        "A$90K-140K",
        ("senior", "au"):     "A$140K-200K",
        ("junior", "global"): "$40K-70K",
        ("mid", "global"):    "$70K-120K",
        ("senior", "global"): "$120K-180K",
    }

    base = salary_table.get((level, region), "$60K-120K")
    qualifier = ""
    if is_product:
        qualifier = " (Product co. — likely higher)"
    elif is_mnc:
        qualifier = " (MNC)"

    return f"~{base}{qualifier} (estimated)"


# ── Company research ────────────────────────────────────────────────────────


def _detect_indian_cities(text: str) -> list[str]:
    """Detect Indian cities from text."""
    text_l = text.lower()
    found = []
    # Normalize aliases
    aliases = {"bangalore": "Bengaluru", "gurgaon": "Gurugram", "trivandrum": "Thiruvananthapuram", "vizag": "Visakhapatnam"}
    for city in INDIAN_CITIES:
        if city in text_l:
            display = aliases.get(city, city.title())
            if display not in found:
                found.append(display)
    return found


def _research_indian_offices(company: str) -> list[str]:
    """Best-effort lookup of Indian office locations via web search."""
    if not company:
        return []
    try:
        query = f"{company} office India locations"
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers={"User-Agent": random.choice(_UA)},
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        snippets = soup.select("a.result__snippet, div.result__snippet")
        all_text = " ".join(s.get_text(strip=True) for s in snippets[:5])
        return _detect_indian_cities(all_text)
    except Exception:
        return []


# ── Main enrichment ─────────────────────────────────────────────────────────


def infer_salary(raw: RawJob, *, web_research: bool = False) -> str:
    """Tiered salary resolution.

    Args:
        raw: The raw job to estimate salary for.
        web_research: If True, attempt DuckDuckGo salary lookup (SLOW —
            adds ~5-15 s per job).  Disabled by default to keep the
            pipeline fast.  Enable only for small batches.
    """
    # 1. Direct from salary field
    if raw.salary_text.strip():
        return raw.salary_text.strip()

    # 2. Regex from description
    found = _extract_salary_from_text(raw.description)
    if found:
        return found

    # 3. Web research (opt-in — very slow for bulk runs)
    if web_research:
        found = _research_salary(raw.company, raw.title)
        if found:
            return found

    # 4. Heuristic estimate (instant)
    return _heuristic_salary(raw.title, raw.company, raw.location)


def enrich_job(raw: RawJob) -> EnrichedJob:
    company_norm = raw.company.strip()
    company_l = company_norm.lower()
    skills = extract_skills(raw.description, raw.title)

    # Indian cities from description/location
    combined_text = f"{raw.description} {raw.location} {raw.title}"
    cities = _detect_indian_cities(combined_text)

    # Web-based Indian office lookup is disabled by default for speed.
    # The heuristic + description/location parsing covers most cases.

    return EnrichedJob(
        source=raw.source,
        external_id=raw.external_id,
        title=raw.title.strip(),
        company=company_norm,
        location=raw.location.strip(),
        description=raw.description.strip(),
        apply_link=raw.apply_link.strip(),
        skills=skills[:5],
        is_mnc=company_l in KNOWN_MNC,
        is_product_based=company_l in KNOWN_PRODUCT,
        indian_cities=cities,
        salary=infer_salary(raw),
        relevance_score=relevance_score(raw.description, raw.title),
        fingerprint=fingerprint(raw),
    )

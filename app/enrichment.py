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
    # Big Tech
    "microsoft", "amazon", "google", "apple", "meta", "facebook",
    # IT Services / Consulting
    "accenture", "ibm", "oracle", "deloitte", "infosys", "tcs",
    "tata consultancy", "wipro", "cognizant", "hcl", "hcl technologies",
    "tech mahindra", "capgemini", "atos", "dxc technology", "ntt data",
    "fujitsu", "hitachi", "samsung", "lti", "ltimindtree", "mphasis",
    "hexaware", "cyient", "mindtree", "birlasoft", "zensar", "coforge",
    "nagarro", "persistent", "persistent systems", "epam", "globant",
    "endava", "publicis sapient", "thoughtworks", "virtusa", "usT",
    "ust global", "sonata software", "mastech", "niit technologies",
    "l&t infotech", "larsen", "kellton", "cigniti", "sasken",
    # Hardware / Chip
    "intel", "cisco", "hp", "hewlett", "dell", "lenovo", "vmware",
    "sap", "ericsson", "nokia", "siemens", "bosch", "continental",
    "thales", "bae systems", "lockheed", "raytheon", "honeywell",
    "ge", "general electric", "schneider", "philips", "lg", "sony",
    "panasonic", "huawei", "zte", "qualcomm", "nvidia", "amd",
    "broadcom", "texas instruments", "micron",
    # Finance / Banking
    "jpmorgan", "jp morgan", "goldman sachs", "morgan stanley",
    "barclays", "hsbc", "citibank", "citi", "citigroup", "deutsche bank",
    "ubs", "credit suisse", "bnp paribas", "standard chartered",
    "nomura", "macquarie", "wells fargo", "bank of america",
    "american express", "amex", "mastercard", "visa",
    # Consulting / Big 4
    "pwc", "pricewaterhouse", "ey", "ernst & young", "ernst young",
    "kpmg", "mckinsey", "bain", "bcg", "boston consulting",
    # FMCG / Pharma / Industrial
    "unilever", "nestle", "procter", "p&g", "johnson & johnson", "j&j",
    "pfizer", "novartis", "roche", "astrazeneca", "merck", "abbott",
    "sanofi", "gsk", "glaxo", "bayer", "eli lilly",
    "shell", "bp", "total", "chevron", "exxon",
    "airbus", "boeing", "rolls-royce", "emerson",
    # Indian MNCs / Large IT
    "reliance", "jio", "bajaj", "mahindra",
    "qualitest", "adp", "experian", "verisk", "gainwell",
    "staples", "xoxoday", "teoco", "bahwan", "ideagen",
    "michael page", "randstad", "manpower", "adecco",
}

KNOWN_PRODUCT = {
    # Global Product Companies
    "microsoft", "google", "apple", "meta", "facebook", "amazon",
    "atlassian", "salesforce", "zoho", "adobe", "sap", "oracle",
    "netflix", "spotify", "uber", "airbnb", "stripe", "shopify",
    "slack", "twilio", "datadog", "snowflake", "hashicorp", "confluent",
    "elastic", "mongodb", "redis", "cockroach labs", "planetscale",
    "figma", "canva", "notion", "miro", "airtable", "asana",
    "github", "gitlab", "jetbrains", "postman", "vercel", "netlify",
    "docker", "vmware", "nutanix", "palo alto", "crowdstrike",
    "zscaler", "okta", "auth0", "cloudflare", "fastly",
    "servicenow", "workday", "veeva", "intuit", "paypal",
    "square", "block", "plaid", "marqeta",
    "nvidia", "qualcomm", "intel", "amd", "broadcom",
    # Indian Product Companies
    "freshworks", "chargebee", "razorpay", "zerodha", "dream11",
    "swiggy", "zomato", "flipkart", "meesho", "cred", "groww",
    "phonepe", "paytm", "ola", "urban company", "dunzo",
    "browserstack", "hasura", "innovaccer", "darwinbox",
    "druva", "icertis", "yellow.ai", "leadsquared", "clevertap",
    "mindtickle", "uniphore", "highradius", "postman",
    "zoho", "freshdesk", "wingify", "instamojo",
    # Data & Analytics Product Companies
    "experian", "verisk", "fico", "dun & bradstreet", "moody",
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


def _is_known_company(company: str, known_set: set[str]) -> bool:
    """Substring-based company matching — handles 'HCL Technologies Limited',
    'Deloitte USI', 'Capgemini Engineering', etc."""
    c = company.lower().strip()
    # Exact match first
    if c in known_set:
        return True
    # Check if any known name is a substring of the company
    for known in known_set:
        if known in c:
            return True
    # Check if company is a substring of any known name
    for known in known_set:
        if c in known and len(c) >= 3:
            return True
    return False


# ── Salary normalization to INR Annual CTC ──────────────────────────────────

_INR_PER_USD = 84
_INR_PER_GBP = 106
_INR_PER_EUR = 92
_INR_PER_AED = 23
_INR_PER_AUD = 55
_INR_PER_SGD = 63
_INR_PER_CAD = 62


def _parse_number(s: str) -> float:
    """Parse a number string like '1,20,000' or '120000' or '120K'."""
    s = s.strip().replace(",", "").replace(" ", "")
    multiplier = 1
    if s.upper().endswith("K"):
        multiplier = 1000
        s = s[:-1]
    elif s.upper().endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return 0


def _normalize_salary_inr(salary_text: str, location: str = "") -> str:
    """Convert any salary format to annual CTC in INR (Lakhs Per Annum).
    Returns empty string if no salary data found."""
    if not salary_text or not salary_text.strip():
        return ""

    text = salary_text.strip()
    loc_l = location.lower()

    # Already in LPA format
    lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?\s*(?:per\s*annum)?|lacs?)", text, re.I)
    if lpa_match:
        lo, hi = float(lpa_match.group(1)), float(lpa_match.group(2))
        return f"₹{lo:.0f}-{hi:.0f} LPA"

    # INR absolute (e.g., ₹12,00,000 - ₹25,00,000)
    inr_abs = re.search(r"(?:inr|₹|rs\.?)\s*(\d[\d,]*)\s*(?:-|to)\s*(?:inr|₹|rs\.?)?\s*(\d[\d,]*)", text, re.I)
    if inr_abs:
        lo = _parse_number(inr_abs.group(1))
        hi = _parse_number(inr_abs.group(2))
        if lo > 0 and hi > 0:
            # Convert to LPA
            lo_lpa = lo / 100_000
            hi_lpa = hi / 100_000
            if lo_lpa < 1:  # Probably already in lakhs
                return f"₹{lo:.0f}-{hi:.0f} LPA"
            return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    # USD
    usd_match = re.search(r"(?:usd|\$)\s*(\d[\d,k]*)\s*(?:-|to)\s*(?:usd|\$)?\s*(\d[\d,k]*)", text, re.I)
    if usd_match:
        lo = _parse_number(usd_match.group(1))
        hi = _parse_number(usd_match.group(2))
        if lo > 0 and hi > 0:
            lo_lpa = (lo * _INR_PER_USD) / 100_000
            hi_lpa = (hi * _INR_PER_USD) / 100_000
            return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    # GBP
    gbp_match = re.search(r"(?:gbp|£)\s*(\d[\d,k]*)\s*(?:-|to)\s*(?:gbp|£)?\s*(\d[\d,k]*)", text, re.I)
    if gbp_match:
        lo = _parse_number(gbp_match.group(1))
        hi = _parse_number(gbp_match.group(2))
        if lo > 0 and hi > 0:
            lo_lpa = (lo * _INR_PER_GBP) / 100_000
            hi_lpa = (hi * _INR_PER_GBP) / 100_000
            return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    # EUR
    eur_match = re.search(r"(?:eur|€)\s*(\d[\d,k]*)\s*(?:-|to)\s*(?:eur|€)?\s*(\d[\d,k]*)", text, re.I)
    if eur_match:
        lo = _parse_number(eur_match.group(1))
        hi = _parse_number(eur_match.group(2))
        if lo > 0 and hi > 0:
            lo_lpa = (lo * _INR_PER_EUR) / 100_000
            hi_lpa = (hi * _INR_PER_EUR) / 100_000
            return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    # AED (monthly → annual)
    aed_match = re.search(r"(?:aed)\s*(\d[\d,k]*)\s*(?:-|to)\s*(?:aed)?\s*(\d[\d,k]*)\s*(?:per\s*month|/month|monthly)?", text, re.I)
    if aed_match:
        lo = _parse_number(aed_match.group(1))
        hi = _parse_number(aed_match.group(2))
        if lo > 0 and hi > 0:
            lo_annual = lo * 12
            hi_annual = hi * 12
            lo_lpa = (lo_annual * _INR_PER_AED) / 100_000
            hi_lpa = (hi_annual * _INR_PER_AED) / 100_000
            return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    # Generic number range with salary context
    generic = re.search(r"(\d[\d,k]*)\s*(?:-|to)\s*(\d[\d,k]*)\s*(?:per year|/year|annually|p\.?a\.?)", text, re.I)
    if generic:
        lo = _parse_number(generic.group(1))
        hi = _parse_number(generic.group(2))
        if lo > 0 and hi > 0:
            # Guess currency from location
            if any(w in loc_l for w in ("india", "bengaluru", "hyderabad", "pune", "mumbai")):
                lo_lpa = lo / 100_000
                hi_lpa = hi / 100_000
                return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"
            else:
                lo_lpa = (lo * _INR_PER_USD) / 100_000
                hi_lpa = (hi * _INR_PER_USD) / 100_000
                return f"₹{lo_lpa:.0f}-{hi_lpa:.0f} LPA"

    return ""


def infer_salary(raw: RawJob, *, web_research: bool = False) -> str:
    """Tiered salary resolution — always returns INR Annual CTC."""
    # 1. Direct from salary field → normalize to INR
    if raw.salary_text.strip():
        normalized = _normalize_salary_inr(raw.salary_text, raw.location)
        if normalized:
            return normalized
        # If normalization failed, it may be experience text — skip it
        exp_like = re.search(r"\d+\s*(?:to|-)\s*\d+\s*(?:yr|year)", raw.salary_text, re.I)
        if not exp_like:
            return raw.salary_text.strip()

    # 2. Regex from description → normalize
    found = _extract_salary_from_text(raw.description)
    if found:
        normalized = _normalize_salary_inr(found, raw.location)
        return normalized if normalized else found

    # 3. Web research (opt-in — very slow for bulk runs)
    if web_research:
        found = _research_salary(raw.company, raw.title)
        if found:
            normalized = _normalize_salary_inr(found, raw.location)
            return normalized if normalized else found

    # 4. Heuristic estimate in INR
    return _heuristic_salary_inr(raw.title, raw.company, raw.location)


def _heuristic_salary_inr(title: str, company: str, location: str) -> str:
    """Fallback salary estimate — always in INR LPA."""
    title_l = title.lower()
    loc_l = location.lower()

    # Determine seniority
    if any(w in title_l for w in ("senior", "sr.", "lead", "principal", "staff", "architect", "manager")):
        level = "senior"
    elif any(w in title_l for w in ("junior", "jr.", "associate", "entry", "trainee", "intern")):
        level = "junior"
    else:
        level = "mid"

    is_mnc = _is_known_company(company, KNOWN_MNC)
    is_product = _is_known_company(company, KNOWN_PRODUCT)

    # Determine region for exchange rate
    if any(w in loc_l for w in ("india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "delhi", "noida", "gurgaon", "gurugram", "chennai", "kolkata", "all india")):
        region = "india"
    elif any(w in loc_l for w in ("uae", "dubai", "abu dhabi", "qatar", "saudi")):
        region = "gulf"
    elif any(w in loc_l for w in ("uk", "london", "united kingdom", "england")):
        region = "uk"
    elif any(w in loc_l for w in ("us", "usa", "united states", "america", "new york", "california", "texas")):
        region = "us"
    elif any(w in loc_l for w in ("australia", "sydney", "melbourne")):
        region = "au"
    elif any(w in loc_l for w in ("europe", "germany", "netherlands", "france", "berlin", "amsterdam")):
        region = "eu"
    elif any(w in loc_l for w in ("singapore",)):
        region = "sg"
    else:
        region = "india"  # Default to India since most jobs are India-targeted

    # Base salary in INR LPA by level + region
    salary_inr: dict[tuple[str, str], tuple[int, int]] = {
        ("junior", "india"):  (5, 12),
        ("mid", "india"):     (12, 25),
        ("senior", "india"):  (25, 50),
        ("junior", "us"):     (50, 75),
        ("mid", "us"):        (75, 120),
        ("senior", "us"):     (120, 185),
        ("junior", "uk"):     (32, 48),
        ("mid", "uk"):        (53, 85),
        ("senior", "uk"):     (85, 138),
        ("junior", "gulf"):   (15, 30),
        ("mid", "gulf"):      (30, 55),
        ("senior", "gulf"):   (55, 90),
        ("junior", "eu"):     (32, 50),
        ("mid", "eu"):        (50, 78),
        ("senior", "eu"):     (78, 120),
        ("junior", "au"):     (33, 50),
        ("mid", "au"):        (50, 77),
        ("senior", "au"):     (77, 110),
        ("junior", "sg"):     (20, 38),
        ("mid", "sg"):        (38, 60),
        ("senior", "sg"):     (60, 95),
    }

    lo, hi = salary_inr.get((level, region), (12, 25))

    # Bump for product/MNC
    if is_product:
        lo = int(lo * 1.3)
        hi = int(hi * 1.3)
    elif is_mnc:
        lo = int(lo * 1.15)
        hi = int(hi * 1.15)

    return f"~₹{lo}-{hi} LPA (est.)"


def enrich_job(raw: RawJob) -> EnrichedJob:
    company_norm = raw.company.strip()
    skills = extract_skills(raw.description, raw.title)

    # Indian cities from description/location
    combined_text = f"{raw.description} {raw.location} {raw.title}"
    cities = _detect_indian_cities(combined_text)

    return EnrichedJob(
        source=raw.source,
        external_id=raw.external_id,
        title=raw.title.strip(),
        company=company_norm,
        location=raw.location.strip(),
        description=raw.description.strip(),
        apply_link=raw.apply_link.strip(),
        skills=skills[:5],
        is_mnc=_is_known_company(company_norm, KNOWN_MNC),
        is_product_based=_is_known_company(company_norm, KNOWN_PRODUCT),
        indian_cities=cities,
        salary=infer_salary(raw),
        experience=raw.experience.strip() if raw.experience else "",
        relevance_score=relevance_score(raw.description, raw.title),
        fingerprint=fingerprint(raw),
    )

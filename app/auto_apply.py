"""Auto-apply engine – Playwright-based form filling for job portals.

Supports per-portal adapters that:
  1. Navigate to the job application page
  2. Auto-fill profile fields (name, email, phone, resume, etc.)
  3. Submit the application or pause for user CAPTCHA solve

Status flow: not_applied → applied / failed
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import PROFILE
from app.db import get_conn

log = logging.getLogger(__name__)


def mark_failed(job_id: int, reason: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status = 'failed' WHERE id = ?", (job_id,))
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, "auto_apply", "failed", reason, datetime.now(timezone.utc).isoformat()),
        )


def mark_applied(job_id: int, portal: str, details: str = "") -> None:
    with get_conn() as conn:
        conn.execute("UPDATE jobs SET status = 'applied' WHERE id = ?", (job_id,))
        conn.execute(
            "INSERT INTO applications(job_id, portal, status, details, attempted_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, portal, "applied", details, datetime.now(timezone.utc).isoformat()),
        )


def _get_browser():
    """Lazy-init a Playwright browser instance."""
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)  # visible so user can solve CAPTCHAs
        return pw, browser
    except Exception as exc:
        log.error("Playwright launch failed: %s  (run: playwright install chromium)", exc)
        return None, None


def _fill_common_fields(page, selectors: dict[str, str]) -> None:
    """Fill common form fields using CSS selectors map."""
    field_map = {
        "name": PROFILE.full_name,
        "full_name": PROFILE.full_name,
        "email": PROFILE.email,
        "phone": PROFILE.phone,
        "mobile": PROFILE.phone,
        "experience": PROFILE.experience_years,
        "current_company": PROFILE.current_company,
        "current_title": PROFILE.current_title,
        "linkedin": PROFILE.linkedin,
        "github": PROFILE.github,
        "location": PROFILE.location,
        "expected_salary": PROFILE.expected_salary,
        "notice_period": PROFILE.notice_period,
        "skills": PROFILE.skills,
    }
    for field_key, css in selectors.items():
        value = field_map.get(field_key, "")
        if value:
            try:
                el = page.query_selector(css)
                if el:
                    el.fill(value)
            except Exception:
                pass


def _upload_resume(page, selector: str) -> None:
    """Upload resume if file exists."""
    resume = Path(PROFILE.resume_path)
    if resume.is_file():
        try:
            page.set_input_files(selector, str(resume))
        except Exception:
            pass


# ── Portal Adapters ─────────────────────────────────────────────────────────


def _apply_linkedin(page, link: str) -> str:
    """LinkedIn Easy Apply flow."""
    page.goto(link, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Click Easy Apply if present
    easy_btn = page.query_selector('button.jobs-apply-button, button[data-control-name="jobdetail_apply"]')
    if easy_btn:
        easy_btn.click()
        page.wait_for_timeout(2000)

    _fill_common_fields(page, {
        "name": 'input[name="name"], input[id*="name"]',
        "email": 'input[name="email"], input[type="email"]',
        "phone": 'input[name="phone"], input[id*="phone"]',
    })
    _upload_resume(page, 'input[type="file"]')

    # Try to click Next / Submit
    for btn_text in ["Submit application", "Submit", "Next", "Review"]:
        btn = page.query_selector(f'button:has-text("{btn_text}")')
        if btn:
            btn.click()
            page.wait_for_timeout(2000)

    return "applied_linkedin"


def _apply_naukri(page, link: str) -> str:
    """Naukri.com apply flow."""
    naukri_email = os.getenv("NAUKRI_EMAIL", "").strip()
    naukri_pass = os.getenv("NAUKRI_PASSWORD", "").strip()

    page.goto(link, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Login if required
    if naukri_email and naukri_pass:
        login_btn = page.query_selector('a[title="Login"], a.login-btn')
        if login_btn:
            login_btn.click()
            page.wait_for_timeout(2000)
            page.fill('input[placeholder*="Email"], input[id="usernameField"]', naukri_email)
            page.fill('input[placeholder*="Password"], input[id="passwordField"]', naukri_pass)
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)

    # Click Apply
    apply_btn = page.query_selector('button.apply-button, button#apply-button, a.apply-btn')
    if apply_btn:
        apply_btn.click()
        page.wait_for_timeout(3000)

    _fill_common_fields(page, {
        "name": 'input[name="name"]',
        "email": 'input[name="email"]',
        "phone": 'input[name="mobile"], input[name="phone"]',
        "experience": 'input[name="experience"]',
        "current_company": 'input[name="currentCompany"]',
        "expected_salary": 'input[name="expectedSalary"]',
        "notice_period": 'input[name="noticePeriod"]',
    })
    _upload_resume(page, 'input[type="file"]')

    submit = page.query_selector('button:has-text("Submit"), button:has-text("Apply")')
    if submit:
        submit.click()
        page.wait_for_timeout(2000)

    return "applied_naukri"


def _apply_indeed(page, link: str) -> str:
    """Indeed apply flow."""
    page.goto(link, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    apply_btn = page.query_selector('button[id="indeedApplyButton"], a.indeed-apply-button, button:has-text("Apply now")')
    if apply_btn:
        apply_btn.click()
        page.wait_for_timeout(3000)

    _fill_common_fields(page, {
        "name": 'input[name="name"], input[id*="name"]',
        "email": 'input[name="email"], input[type="email"]',
        "phone": 'input[name="phone"]',
    })
    _upload_resume(page, 'input[type="file"]')

    return "applied_indeed"


def _apply_generic(page, link: str) -> str:
    """Generic portal – navigate, try to find and fill apply form."""
    page.goto(link, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Try clicking any Apply button
    for selector in ['button:has-text("Apply")', 'a:has-text("Apply")',
                      'button:has-text("Submit")', 'a.apply-btn']:
        btn = page.query_selector(selector)
        if btn:
            btn.click()
            page.wait_for_timeout(2000)
            break

    # Try to fill common fields
    _fill_common_fields(page, {
        "name": 'input[name*="name"], input[placeholder*="name"]',
        "email": 'input[type="email"], input[name*="email"]',
        "phone": 'input[name*="phone"], input[placeholder*="phone"]',
    })
    _upload_resume(page, 'input[type="file"]')

    return "applied_generic"


# ── Dispatcher ──────────────────────────────────────────────────────────────

PORTAL_ADAPTERS = {
    "linkedin.com": _apply_linkedin,
    "naukri.com": _apply_naukri,
    "indeed.com": _apply_indeed,
    "indeed.co.in": _apply_indeed,
    "indeed.co.uk": _apply_indeed,
    "indeed.ae": _apply_indeed,
}


def apply_to_job(job_id: int) -> str:
    """Attempt to auto-apply to a job using Playwright."""
    with get_conn() as conn:
        row = conn.execute("SELECT apply_link, title, company FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return "job_not_found"

    link = row["apply_link"]
    host = urlparse(link).netloc.lower()

    # Find matching adapter
    adapter = _apply_generic
    for domain, fn in PORTAL_ADAPTERS.items():
        if domain in host:
            adapter = fn
            break

    pw, browser = _get_browser()
    if not browser:
        mark_failed(job_id, "Playwright browser unavailable. Run: playwright install chromium")
        return "failed_no_browser"

    try:
        page = browser.new_page()
        result = adapter(page, link)
        mark_applied(job_id, host, result)
        log.info("Auto-applied to job %d (%s) via %s", job_id, row["title"], host)
        return result
    except Exception as exc:
        mark_failed(job_id, str(exc))
        log.warning("Auto-apply failed for job %d: %s", job_id, exc)
        return f"failed_{exc}"
    finally:
        try:
            browser.close()
            pw.stop()
        except Exception:
            pass

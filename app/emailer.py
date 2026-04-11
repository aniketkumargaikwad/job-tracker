"""Email digest builder – rich HTML table with Apply buttons.

Columns: Sr.No | Job Title | Company | 5 Key Skills | isMNC | isProductBased |
         Indian Cities | Apply Link | Salary

The Apply link points to the local web dashboard auto-apply endpoint so that
clicking it triggers profile auto-fill via Playwright.  A fallback direct
portal link is also provided.
"""
from __future__ import annotations

import html
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import SETTINGS


def _esc(value: str) -> str:
    return html.escape(str(value))


def build_html(rows: list[dict]) -> str:
    dashboard_base = SETTINGS.dashboard_url or f"http://{SETTINGS.dashboard_host}:{SETTINGS.dashboard_port}"
    today = datetime.now().strftime("%B %d, %Y")

    table_rows = []
    for idx, row in enumerate(rows, start=1):
        auto_link = f"{dashboard_base}/apply/{row.get('job_id', '')}"
        portal_link = _esc(row.get("link", "#"))
        table_rows.append(f"""
        <tr style="border-bottom:1px solid #333;">
          <td style="padding:8px;text-align:center;color:#0f0;">{idx}</td>
          <td style="padding:8px;">{_esc(row['title'])}</td>
          <td style="padding:8px;">{_esc(row['company'])}</td>
          <td style="padding:8px;font-size:12px;">{_esc(row['skills'])}</td>
          <td style="padding:8px;text-align:center;">{_esc(row['is_mnc'])}</td>
          <td style="padding:8px;text-align:center;">{_esc(row['is_product'])}</td>
          <td style="padding:8px;font-size:12px;">{_esc(row['cities'])}</td>
          <td style="padding:8px;text-align:center;">
            <a href="{auto_link}" style="background:#0f0;color:#000;padding:6px 12px;
               text-decoration:none;border-radius:4px;font-weight:bold;font-size:12px;
               display:inline-block;margin-bottom:4px;">⚡ Quick Apply</a><br>
            <a href="{portal_link}" style="color:#0f0;font-size:11px;">Portal ↗</a>
          </td>
          <td style="padding:8px;font-size:12px;">{_esc(row['salary'])}</td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;background:#0a0a0a;color:#c0c0c0;font-family:'Courier New',monospace;">
  <div style="max-width:1200px;margin:0 auto;">
    <h2 style="color:#0f0;border-bottom:2px solid #0f0;padding-bottom:10px;">
      ⚡ Daily Remote .NET Jobs Digest — {today}
    </h2>
    <p style="color:#888;font-size:13px;">
      {len(rows)} new jobs found | Skills: .NET, C#, Angular, Microservices |
      <a href="{dashboard_base}" style="color:#0f0;">Open Dashboard</a>
    </p>

    <table style="width:100%;border-collapse:collapse;background:#111;border:1px solid #333;font-size:13px;">
      <thead>
        <tr style="background:#1a1a1a;color:#0f0;text-transform:uppercase;font-size:11px;">
          <th style="padding:10px;">Sr.No</th>
          <th style="padding:10px;text-align:left;">Job Title</th>
          <th style="padding:10px;text-align:left;">Company</th>
          <th style="padding:10px;text-align:left;">5 Key Skills</th>
          <th style="padding:10px;">MNC?</th>
          <th style="padding:10px;">Product?</th>
          <th style="padding:10px;text-align:left;">Indian Cities</th>
          <th style="padding:10px;">Apply</th>
          <th style="padding:10px;text-align:left;">Salary</th>
        </tr>
      </thead>
      <tbody>
        {''.join(table_rows)}
      </tbody>
    </table>

    <p style="color:#555;font-size:11px;margin-top:20px;">
      ⚡ Quick Apply opens your local dashboard and auto-fills your profile.<br>
      Portal ↗ opens the job posting directly on the source website.<br>
      Ensure the dashboard is running: <code style="color:#0f0;">python main.py web</code>
    </p>
  </div>
</body>
</html>"""


def send_email(rows: list[dict]) -> None:
    if not rows or not SETTINGS.email_host:
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[{len(rows)} Jobs] Daily Remote .NET Digest — {datetime.now().strftime('%b %d')}"
    msg["From"] = SETTINGS.email_from
    msg["To"] = SETTINGS.email_to
    msg.attach(MIMEText(build_html(rows), "html"))

    with smtplib.SMTP(SETTINGS.email_host, SETTINGS.email_port) as server:
        server.starttls()
        server.login(SETTINGS.email_user, SETTINGS.email_password)
        server.sendmail(SETTINGS.email_from, [SETTINGS.email_to], msg.as_string())

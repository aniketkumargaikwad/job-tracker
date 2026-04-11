# Fully Automated Remote Job Aggregation System (Zero Cost)

A complete job automation pipeline that collects remote .NET/C#/Angular/Microservices jobs from **20+ sources worldwide**, deduplicates them, enriches with salary research & company data, emails a daily digest at **7:00 AM IST**, and provides **one-click auto-apply** via a terminal-themed web dashboard.

**Every component is free — no credit card required anywhere.**

---

## Features

### Multi-Source Job Collection (20+ sources)

**Tier 1 — Free Open APIs (no key needed):**
| Source | Coverage |
|--------|----------|
| Remotive | Global remote jobs |
| RemoteOK | Global remote tech |
| Arbeitnow | EU + remote jobs |
| Himalayas | Remote-first companies |
| Jobicy | Remote developer roles |
| The Muse | US + global companies |
| FindWork.dev | Developer-focused roles |
| JoBoard | Aggregated listings |

**Tier 2 — Free API Key (register, no CC):**
| Source | Coverage | Registration |
|--------|----------|-------------|
| Adzuna | IN, GB, US, AU, DE, AE, CA, NL, SG | https://developer.adzuna.com |
| Reed.co.uk | UK jobs | https://www.reed.co.uk/developers/jobseeker |
| Jooble | Global aggregator | https://jooble.org/api/about |

**Tier 3 — Web Scraping (best effort):**
| Source | Coverage |
|--------|----------|
| LinkedIn | Global (public search) |
| Indeed | IN, US, UK, AU, AE, CA, DE, NL, SG |
| Naukri.com | India-focused |
| SimplyHired | US + global |
| GulfTalent | UAE / Middle East |
| Bayt.com | Middle East |
| CWJobs | UK tech jobs |
| Wellfound | Startup jobs |
| Glassdoor | Global (public search) |
| DuckDuckGo | Backup aggregator search |

### Smart Filtering & Deduplication
- **Primary skills**: .NET, .NET Core, C#, Microservices, Angular
- **Secondary skills**: ASP.NET, Web API, Azure, Docker, K8s, SQL Server, Entity Framework, Blazor, etc.
- **Fingerprint dedup**: SHA-256 of (title + company + link) — exact match prevention
- **Fuzzy dedup**: RapidFuzz token_set_ratio ≥ 90% — catches reposts with minor title changes
- **Once emailed = never re-sent**: Previous jobs are permanently excluded from future digests

### Enrichment & Salary Research
- **Salary (4-tier resolution)**:
  1. Direct from job description
  2. Regex extraction (INR/USD/GBP/AED/EUR patterns)
  3. Web research via DuckDuckGo → Glassdoor/AmbitionBox snippets
  4. Heuristic estimate (role level × company type × region)
- **MNC detection**: 100+ known MNCs
- **Product company detection**: 80+ known product companies
- **Indian office cities**: 25+ cities detected from description + web research

### Daily Email Digest
- Rich HTML email with dark theme styling
- Table columns: **Sr.No | Job Title | Company | 5 Key Skills | isMNC | isProductBased | Indian Cities | Apply Link | Salary**
- **Quick Apply button** → opens web dashboard auto-apply
- **Portal link** → opens job posting directly
- Sent daily at **7:00 AM IST**

### One-Click Auto-Apply (Playwright)
- Per-portal adapters: LinkedIn Easy Apply, Naukri, Indeed, + generic
- Auto-fills: name, email, phone, experience, resume upload
- Visible browser (non-headless) so you can solve CAPTCHAs
- Status tracking: applied / failed with detailed logs

### Terminal-Themed Web Dashboard
- **Green-on-black terminal aesthetic** with monospace font
- Routes: `/` (jobs), `/history` (applications), `/stats` (analytics)
- Search/filter across all jobs
- One-click apply from the dashboard
- JSON APIs: `/api/jobs`, `/api/history`, `/api/stats`

### TUI Dashboard (textual)
- Terminal-based alternative using the `textual` library
- Filter and browse jobs without a browser

---

## Free Infrastructure Stack (No Credit Card)

| Component | Technology | Cost |
|-----------|-----------|------|
| Database | SQLite (local file) | Free |
| Backend | Python scripts | Free |
| Scheduler | APScheduler (local process) OR Windows Task Scheduler | Free |
| Email | Gmail SMTP (App Password) | Free |
| Web scraping | requests + BeautifulSoup + lxml | Free |
| Auto-apply | Playwright (Chromium) | Free |
| Web dashboard | Flask (localhost) | Free |
| TUI dashboard | Textual (terminal) | Free |

---

## Setup (Step by Step)

### 1. Create virtual environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Playwright browser (for auto-apply)
```bash
playwright install chromium
```

### 4. Configure environment
```bash
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
```

Edit `.env` with your settings:

**Required:**
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` — Gmail: enable 2FA → create App Password at https://myaccount.google.com/apppasswords
- `EMAIL_FROM`, `EMAIL_TO` — sender and recipient email addresses

**Recommended (for auto-apply):**
- `PROFILE_*` fields — your name, email, phone, resume path, etc.
- Portal credentials (`NAUKRI_EMAIL`, `LINKEDIN_EMAIL`, etc.)

**Optional (for more sources):**
- `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` — register free at https://developer.adzuna.com
- `REED_API_KEY` — register free at https://www.reed.co.uk/developers/jobseeker
- `JOOBLE_API_KEY` — register free at https://jooble.org/api/about

### 5. Place your resume
```bash
mkdir data
# Copy your resume to data/resume.pdf
# Optionally: data/cover_letter.txt
```

---

## Usage

### Run pipeline once (with email)
```bash
python main.py run
```

### Run pipeline once (no email — test mode)
```bash
python main.py run-no-email
```

### Start daily scheduler (7:00 AM IST)
```bash
python scheduler.py
```

### Start web dashboard
```bash
python main.py web
# Opens at http://127.0.0.1:5000
```

### Start terminal (TUI) dashboard
```bash
python main.py dashboard
```

### Auto-apply for a specific job
```bash
python main.py apply --job-id 42
```

### Alternative: Windows Task Scheduler (always free)
Instead of keeping `scheduler.py` running, create a Windows Scheduled Task:
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily at 7:00 AM
3. Action: Start a program
4. Program: `path\to\.venv\Scripts\python.exe`
5. Arguments: `main.py run`
6. Start in: `path\to\Cursor1`

---

## Data Model

| Table | Purpose |
|-------|---------|
| `jobs` | All collected jobs with enriched fields, fingerprint, score, status |
| `run_log` | Per-run metrics (fetched/stored counts, timing, errors) |
| `applications` | Email/apply attempts with status and timestamps |

---

## Architecture

```
                    ┌─────────────┐
                    │  Scheduler  │  (7:00 AM IST)
                    │ APScheduler │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Pipeline  │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
  │  API       │    │  Scrapers   │    │  Keyed APIs │
  │  Sources   │    │  (LinkedIn, │    │  (Adzuna,   │
  │  (8 free)  │    │  Indeed,    │    │  Reed,      │
  │            │    │  Naukri...) │    │  Jooble)    │
  └─────┬─────┘    └──────┬──────┘    └──────┬──────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Scoring &  │
                    │  Filtering  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Dedup      │
                    │  (fingerprint│
                    │  + fuzzy)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Enrichment │
                    │  (salary,   │
                    │  MNC, cities)│
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐  ┌─▼──┐  ┌─────▼──────┐
       │  SQLite DB  │  │Email│  │ Web Dashboard│
       │  (persist)  │  │Digest│ │ (Flask)     │
       └─────────────┘  └────┘  └─────────────┘
```

---

## Tests
```bash
python -m pytest
```

---

## Troubleshooting

| Issue | Solution |
|-------|---------|
| No jobs collected | Check internet; some scrapers may be blocked — API sources should still work |
| Email not sent | Verify SMTP settings; Gmail needs App Password (not regular password) |
| Playwright fails | Run `playwright install chromium` |
| No salary data | Enable Adzuna API key; salary research uses DuckDuckGo (may be rate-limited) |
| Dashboard won't start | Check port 5000 is free; change `DASHBOARD_PORT` in `.env` |

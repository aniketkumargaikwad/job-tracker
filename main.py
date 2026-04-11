from __future__ import annotations

import argparse
import json
import logging

from app.auto_apply import apply_to_job
from app.dashboard import run_dashboard
from app.pipeline import run_pipeline
from app.web_dashboard import run_web_dashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _safe_print(text: str) -> None:
    """Print with fallback for Windows terminals that can't handle Unicode."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _print_summary(result: dict) -> None:
    """Print a terminal-friendly job summary table."""
    jobs = result.get("jobs", [])

    # ── Stats banner ────────────────────────────────────────────────
    _safe_print("")
    _safe_print("=" * 100)
    _safe_print(f"  PIPELINE SUMMARY  |  Fetched: {result['fetched']}  |  "
          f"Saved: {result['saved']}  |  Dups: {result['skipped_dup']}  |  "
          f"Filtered: {result['skipped_filter']}  |  "
          f"Emailed: {result.get('emailed', 0)}  |  "
          f"Time: {result.get('time_seconds', '?')}s")
    _safe_print("=" * 100)

    if not jobs:
        _safe_print("  No new relevant jobs found in this run.")
        _safe_print("=" * 100)
        return

    # ── Table header ────────────────────────────────────────────────
    hdr = (f"{'#':>3}  {'Title':<40}  {'Company':<20}  {'Skills':<30}  "
           f"{'MNC':>3}  {'Prod':>4}  {'Cities':<15}  {'Salary':<25}  {'Score':>5}  {'Source':<12}")
    _safe_print(hdr)
    _safe_print("-" * len(hdr))

    # ── Table rows ──────────────────────────────────────────────────
    for idx, j in enumerate(jobs, 1):
        title = j["title"][:38] + ".." if len(j["title"]) > 40 else j["title"]
        company = j["company"][:18] + ".." if len(j["company"]) > 20 else j["company"]
        skills = j["skills"][:28] + ".." if len(j["skills"]) > 30 else j["skills"]
        cities = j["cities"][:13] + ".." if len(j["cities"]) > 15 else j["cities"]
        salary = j["salary"][:23] + ".." if len(j["salary"]) > 25 else j["salary"]
        source = j["source"][:12]
        _safe_print(f"{idx:>3}  {title:<40}  {company:<20}  {skills:<30}  "
              f"{j['is_mnc']:>3}  {j['is_product']:>4}  {cities:<15}  "
              f"{salary:<25}  {j['score']:>5.0f}  {source:<12}")

    _safe_print("-" * len(hdr))
    _safe_print(f"  Total: {len(jobs)} jobs  |  Apply links saved in database -- "
          f"run 'python main.py web' to browse")
    _safe_print("=" * 100)
    _safe_print("")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Remote job automation system")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Fetch/filter/dedupe/enrich/send email")
    sub.add_parser("run-no-email", help="Fetch/filter/dedupe/enrich only (no email)")
    sub.add_parser("dashboard", help="Open terminal (TUI) dashboard")
    sub.add_parser("web", help="Start web dashboard (http://localhost:5000)")
    apply_cmd = sub.add_parser("apply", help="Auto-apply for one job")
    apply_cmd.add_argument("--job-id", type=int, required=True)
    sub.add_parser("json", help="Run pipeline and output raw JSON (for scripting)")
    args = parser.parse_args()

    if args.command == "run":
        result = run_pipeline(send_mail=True)
        _print_summary(result)
    elif args.command == "run-no-email":
        result = run_pipeline(send_mail=False)
        _print_summary(result)
    elif args.command == "json":
        result = run_pipeline(send_mail=False)
        del result["jobs"]  # strip large payload for JSON mode
        print(json.dumps(result, indent=2))
    elif args.command == "dashboard":
        run_dashboard()
    elif args.command == "web":
        run_web_dashboard()
    elif args.command == "apply":
        print(apply_to_job(args.job_id))
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()

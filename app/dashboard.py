from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Input

from app.db import get_conn, init_db


class JobsDashboard(App):
    CSS = """
    Screen { background: black; color: green; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Filter by title/company...", id="filter")
        yield DataTable(id="jobs")
        yield Footer()

    def on_mount(self) -> None:
        init_db()
        table = self.query_one("#jobs", DataTable)
        table.add_columns("ID", "Title", "Company", "Skills", "Status", "Score")
        self._load_rows("")

    def _load_rows(self, query: str) -> None:
        table = self.query_one("#jobs", DataTable)
        table.clear()
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, title, company, skills_csv, status, relevance_score
                FROM jobs
                WHERE lower(title) LIKE ? OR lower(company) LIKE ?
                ORDER BY id DESC
                LIMIT 500
                """,
                (f"%{query.lower()}%", f"%{query.lower()}%"),
            ).fetchall()
        for r in rows:
            table.add_row(str(r["id"]), r["title"], r["company"], r["skills_csv"], r["status"], f"{r['relevance_score']:.1f}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self._load_rows(event.value.strip())


def run_dashboard() -> None:
    JobsDashboard().run()

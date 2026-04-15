"""Tests for main.py CLI interface."""
from unittest.mock import MagicMock, patch

import pytest


class TestCli:
    @patch("main.run_pipeline", return_value={"fetched": 0, "saved": 0, "emailed": 0, "skipped_dup": 0, "skipped_filter": 0, "time_seconds": 0, "jobs": []})
    def test_run_command(self, mock_pipeline):
        import sys
        with patch.object(sys, "argv", ["main.py", "run"]):
            from main import cli
            cli()
        mock_pipeline.assert_called_once_with(send_mail=True)

    @patch("main.run_pipeline", return_value={"fetched": 0, "saved": 0, "emailed": 0, "skipped_dup": 0, "skipped_filter": 0, "time_seconds": 0, "jobs": []})
    def test_run_no_email_command(self, mock_pipeline):
        import sys
        with patch.object(sys, "argv", ["main.py", "run-no-email"]):
            from main import cli
            cli()
        mock_pipeline.assert_called_once_with(send_mail=False)

    def test_no_command_prints_help(self, capsys):
        import sys
        with patch.object(sys, "argv", ["main.py"]):
            from main import cli
            cli()
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "help" in captured.out.lower() or "Remote job" in captured.out

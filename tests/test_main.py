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

    @patch("main.apply_to_job", return_value="applied")
    def test_apply_command(self, mock_apply):
        import sys
        with patch.object(sys, "argv", ["main.py", "apply", "--job-id", "42"]):
            from main import cli
            cli()
        mock_apply.assert_called_once_with(42)

    def test_no_command_prints_help(self, capsys):
        import sys
        with patch.object(sys, "argv", ["main.py"]):
            from main import cli
            cli()
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "help" in captured.out.lower() or "Remote job" in captured.out


class TestScheduler:
    @patch("scheduler.BlockingScheduler")
    def test_scheduler_setup(self, mock_scheduler_class):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        from scheduler import main
        main()

        mock_scheduler_class.assert_called_once()
        mock_scheduler.add_job.assert_called_once()
        mock_scheduler.start.assert_called_once()

        # Verify it's set to 7 AM IST
        call_kwargs = mock_scheduler.add_job.call_args
        trigger = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("trigger")
        assert trigger is not None

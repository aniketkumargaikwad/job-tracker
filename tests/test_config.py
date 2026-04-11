"""Tests for app.config – Settings and UserProfile loading."""
import os
from unittest.mock import patch

from app.config import Settings, UserProfile, _env, _list_env


class TestEnvHelpers:
    def test_list_env_with_values(self):
        with patch.dict(os.environ, {"TEST_LIST": "a, b, c"}):
            result = _list_env("TEST_LIST")
            assert result == ["a", "b", "c"]

    def test_list_env_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_MISSING", None)
            result = _list_env("TEST_MISSING")
            assert result == []

    def test_list_env_default(self):
        os.environ.pop("TEST_MISSING2", None)
        result = _list_env("TEST_MISSING2", "x,y")
        assert result == ["x", "y"]

    def test_list_env_strips_whitespace(self):
        with patch.dict(os.environ, {"TEST_WS": "  hello , world  "}):
            result = _list_env("TEST_WS")
            assert result == ["hello", "world"]

    def test_list_env_skips_empty_items(self):
        with patch.dict(os.environ, {"TEST_EMPTY": "a,,b,  ,c"}):
            result = _list_env("TEST_EMPTY")
            assert result == ["a", "b", "c"]

    def test_env_returns_value(self):
        with patch.dict(os.environ, {"MY_VAR": " hello "}):
            assert _env("MY_VAR") == "hello"

    def test_env_returns_default(self):
        os.environ.pop("NONEXISTENT_VAR", None)
        assert _env("NONEXISTENT_VAR", "fallback") == "fallback"

    def test_env_returns_empty_string_default(self):
        os.environ.pop("NONEXISTENT_VAR2", None)
        assert _env("NONEXISTENT_VAR2") == ""


class TestSettings:
    def test_settings_frozen(self):
        s = Settings()
        import pytest
        with pytest.raises(AttributeError):
            s.email_host = "changed"  # type: ignore[misc]

    def test_settings_db_path_default(self):
        s = Settings()
        assert str(s.db_path).endswith("jobs.db")

    def test_settings_email_port_default(self):
        s = Settings()
        assert s.email_port == 587

    def test_settings_lists_populated(self):
        s = Settings()
        assert isinstance(s.target_roles, list)
        assert isinstance(s.title_blacklist, list)
        assert isinstance(s.excluded_companies, list)

    def test_settings_dashboard_defaults(self):
        s = Settings()
        assert s.dashboard_host == "127.0.0.1"
        assert s.dashboard_port == 5000


class TestUserProfile:
    def test_profile_frozen(self):
        p = UserProfile()
        import pytest
        with pytest.raises(AttributeError):
            p.full_name = "changed"  # type: ignore[misc]

    def test_profile_defaults(self):
        p = UserProfile()
        assert p.experience_years == "5"
        assert p.resume_path == "data/resume.pdf"

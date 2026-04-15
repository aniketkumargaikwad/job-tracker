from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _list_env(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default).strip()
    return [item.strip() for item in value.split(",") if item.strip()]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # SMTP
    email_host: str = _env("SMTP_HOST")
    email_port: int = int(_env("SMTP_PORT", "587"))
    email_user: str = _env("SMTP_USER")
    email_password: str = _env("SMTP_PASSWORD")
    email_from: str = _env("EMAIL_FROM")
    email_to: str = _env("EMAIL_TO")

    # Optional API keys (free tiers)
    adzuna_app_id: str = _env("ADZUNA_APP_ID")
    adzuna_app_key: str = _env("ADZUNA_APP_KEY")
    reed_api_key: str = _env("REED_API_KEY")
    jooble_api_key: str = _env("JOOBLE_API_KEY")

    # Dashboard
    dashboard_host: str = _env("DASHBOARD_HOST", "0.0.0.0")
    dashboard_port: int = int(_env("DASHBOARD_PORT", "5000"))
    dashboard_url: str = _env("DASHBOARD_URL", "")

    # Lists – populated in __post_init__
    target_roles: list[str] = None  # type: ignore[assignment]
    preferred_countries: list[str] = None  # type: ignore[assignment]
    excluded_companies: list[str] = None  # type: ignore[assignment]
    priority_companies: list[str] = None  # type: ignore[assignment]
    title_blacklist: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_roles", _list_env("TARGET_ROLES", ".NET Developer"))
        object.__setattr__(self, "preferred_countries", _list_env("PREFERRED_COUNTRIES", "India"))
        object.__setattr__(self, "excluded_companies", _list_env("EXCLUDED_COMPANIES"))
        object.__setattr__(self, "priority_companies", _list_env("PRIORITY_COMPANIES"))
        object.__setattr__(self, "title_blacklist", _list_env("JOB_TITLE_BLACKLIST"))


@dataclass(frozen=True)
class UserProfile:
    full_name: str = _env("PROFILE_FULL_NAME")
    email: str = _env("PROFILE_EMAIL")
    phone: str = _env("PROFILE_PHONE")
    location: str = _env("PROFILE_LOCATION")
    experience_years: str = _env("PROFILE_EXPERIENCE_YEARS", "5")
    current_title: str = _env("PROFILE_CURRENT_TITLE")
    linkedin: str = _env("PROFILE_LINKEDIN")
    github: str = _env("PROFILE_GITHUB")
    skills: str = _env("PROFILE_SKILLS")
    current_company: str = _env("PROFILE_CURRENT_COMPANY")
    current_salary: str = _env("PROFILE_CURRENT_SALARY")
    expected_salary: str = _env("PROFILE_EXPECTED_SALARY")
    notice_period: str = _env("PROFILE_NOTICE_PERIOD")
    work_auth: str = _env("PROFILE_WORK_AUTH")


SETTINGS = Settings()
PROFILE = UserProfile()

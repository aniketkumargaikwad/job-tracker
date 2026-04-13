from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RawJob:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    description: str
    apply_link: str
    posted_at: str = ""
    salary_text: str = ""
    experience: str = ""

    def is_valid(self) -> bool:
        """Check minimum required fields are present."""
        return bool(self.title and self.company and self.apply_link)


@dataclass
class EnrichedJob:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    description: str
    apply_link: str
    skills: list[str]
    is_mnc: bool
    is_product_based: bool
    indian_cities: list[str]
    salary: str
    experience: str
    relevance_score: float
    fingerprint: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

"""Tests for app.scoring – skill extraction, relevance, fingerprint, dedup."""
import pytest

from app.models import RawJob
from app.scoring import (
    extract_skills,
    fingerprint,
    is_likely_duplicate,
    normalize_text,
    relevance_score,
)


class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("HELLO World") == "hello world"

    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self):
        assert normalize_text("hello   world   foo") == "hello world foo"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_already_normalized(self):
        assert normalize_text("hello world") == "hello world"


class TestFingerprint:
    def test_deterministic(self):
        raw = RawJob("src", "1", "Dev", "Acme", "Remote", "desc", "https://x.com/apply")
        fp1 = fingerprint(raw)
        fp2 = fingerprint(raw)
        assert fp1 == fp2

    def test_sha256_length(self):
        raw = RawJob("src", "1", "Dev", "Acme", "Remote", "desc", "https://x.com/apply")
        assert len(fingerprint(raw)) == 64

    def test_different_jobs_different_fingerprints(self):
        raw1 = RawJob("src", "1", "Dev A", "Acme", "Remote", "desc", "https://x.com/1")
        raw2 = RawJob("src", "2", "Dev B", "Beta", "Remote", "desc", "https://x.com/2")
        assert fingerprint(raw1) != fingerprint(raw2)

    def test_case_insensitive(self):
        raw1 = RawJob("src", "1", "Dev", "Acme", "", "", "https://x.com")
        raw2 = RawJob("src", "1", "DEV", "ACME", "", "", "https://X.COM")
        assert fingerprint(raw1) == fingerprint(raw2)

    def test_whitespace_insensitive(self):
        raw1 = RawJob("src", "1", "Senior Dev", "Acme Corp", "", "", "https://x.com")
        raw2 = RawJob("src", "1", "  Senior  Dev ", " Acme  Corp ", "", "", " https://x.com ")
        assert fingerprint(raw1) == fingerprint(raw2)


class TestExtractSkills:
    def test_top5(self):
        text = "We need C#, .NET Core, Angular, Azure, Docker and SQL Server experience."
        skills = extract_skills(text, "Senior .NET Engineer")
        assert ".net core" in skills or ".net" in skills
        assert "c#" in skills
        assert len(skills) <= 5

    def test_primary_skills_weighted_higher(self):
        text = "C# developer with angular and microservices"
        skills = extract_skills(text, ".NET Developer")
        assert skills[0] in [".net", ".net core", "c#", "microservices", "angular"]

    def test_empty_description(self):
        skills = extract_skills("", "")
        assert skills == []

    def test_no_matching_skills(self):
        skills = extract_skills("Python Django Flask", "Python Developer")
        assert skills == []

    def test_secondary_skills_detected(self):
        text = "Azure Docker Kubernetes SQL Server Entity Framework"
        skills = extract_skills(text, "Cloud Engineer")
        assert len(skills) >= 3

    def test_synonyms_detected(self):
        text = "Experience with dotnet, csharp, and k8s"
        skills = extract_skills(text, "Software Engineer")
        assert any(s in skills for s in [".net", "c#", "kubernetes"])

    def test_title_contributes_to_skills(self):
        skills = extract_skills("", ".NET Core Angular Developer")
        assert ".net core" in skills or "angular" in skills


class TestRelevanceScore:
    def test_high_score_with_all_primary(self):
        score = relevance_score(
            "Remote role using .NET Core C# microservices angular",
            "Backend Engineer"
        )
        assert score >= 40

    def test_low_score_irrelevant(self):
        raw = RawJob("x", "1", "Graphic Designer", "Acme", "Remote", "Photoshop and Figma", "https://x.com")
        score = relevance_score(raw.description, raw.title)
        assert score < 40

    def test_remote_keyword_bonus(self):
        base = relevance_score(".NET developer", "Dev")
        remote = relevance_score(".NET developer remote", "Dev")
        assert remote > base

    def test_india_keyword_bonus(self):
        base = relevance_score(".NET developer", "Dev")
        india = relevance_score(".NET developer India", "Dev")
        assert india > base

    def test_wfh_keyword_bonus(self):
        base = relevance_score(".NET developer", "Dev")
        wfh = relevance_score(".NET developer work from home", "Dev")
        assert wfh > base

    def test_max_100(self):
        text = ".NET .NET Core C# microservices angular asp.net web api azure docker kubernetes sql server remote india worldwide fully remote work from home entity framework blazor signalr"
        score = relevance_score(text, ".NET Core Angular Microservices Developer")
        assert score <= 100.0

    def test_zero_for_empty(self):
        assert relevance_score("", "") == 0.0

    def test_secondary_skills_contribute(self):
        score = relevance_score("Azure Docker Kubernetes experience required", "DevOps")
        assert score > 0


class TestIsLikelyDuplicate:
    def test_exact_match(self):
        raw = RawJob("src", "1", "Senior .NET Developer", "Microsoft", "Remote", "desc", "https://x.com")
        existing = [("Senior .NET Developer", "Microsoft")]
        assert is_likely_duplicate(raw, existing) is True

    def test_no_match(self):
        raw = RawJob("src", "1", "Angular Developer", "Google", "Remote", "desc", "https://x.com")
        existing = [("Backend Python Dev", "Amazon")]
        assert is_likely_duplicate(raw, existing) is False

    def test_fuzzy_title_same_company(self):
        raw = RawJob("src", "1", "Senior .NET Developer (Remote)", "Microsoft", "Remote", "desc", "https://x.com")
        existing = [("Senior .NET Developer", "Microsoft")]
        assert is_likely_duplicate(raw, existing) is True

    def test_different_company_no_match(self):
        raw = RawJob("src", "1", "Senior .NET Developer", "Apple", "Remote", "desc", "https://x.com")
        existing = [("Senior .NET Developer", "Microsoft")]
        assert is_likely_duplicate(raw, existing) is False

    def test_empty_existing(self):
        raw = RawJob("src", "1", "Dev", "Co", "Remote", "desc", "https://x.com")
        assert is_likely_duplicate(raw, []) is False

    def test_very_similar_title_and_company(self):
        raw = RawJob("src", "1", ".NET Core Developer - Remote", "Acme Inc",
                      "Remote", "desc", "https://x.com")
        existing = [(".NET Core Developer - Remote", "Acme Inc.")]
        assert is_likely_duplicate(raw, existing) is True

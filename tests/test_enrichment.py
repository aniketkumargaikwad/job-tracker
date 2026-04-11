"""Tests for app.enrichment – salary inference, MNC detection, city detection."""
from unittest.mock import MagicMock, patch

import pytest

from app.enrichment import (
    _detect_indian_cities,
    _extract_salary_from_text,
    _heuristic_salary,
    enrich_job,
    infer_salary,
    KNOWN_MNC,
    KNOWN_PRODUCT,
)
from app.models import RawJob


class TestExtractSalaryFromText:
    def test_inr_lpa_format(self):
        result = _extract_salary_from_text("Salary: ₹15 - 25 LPA based on experience")
        assert result != ""
        assert "15" in result

    def test_usd_k_format(self):
        result = _extract_salary_from_text("Compensation: $80,000 - $120,000 per year")
        assert result != ""

    def test_gbp_format(self):
        result = _extract_salary_from_text("Salary: £50,000 - £80,000 per annum")
        assert result != ""

    def test_aed_format(self):
        result = _extract_salary_from_text("AED 15000 - 30000 per month")
        assert result != ""

    def test_eur_format(self):
        result = _extract_salary_from_text("€55,000 - €85,000 per year")
        assert result != ""

    def test_no_salary_found(self):
        result = _extract_salary_from_text("Great opportunity for passionate developers")
        assert result == ""

    def test_generic_salary_range(self):
        result = _extract_salary_from_text("salary: 50000-80000")
        assert result != ""

    def test_empty_text(self):
        assert _extract_salary_from_text("") == ""


class TestHeuristicSalary:
    def test_senior_india(self):
        result = _heuristic_salary("Senior .NET Developer", "Microsoft", "Bengaluru, India")
        assert "22-45 LPA" in result or "estimated" in result.lower()

    def test_junior_us(self):
        result = _heuristic_salary("Junior Developer", "Google", "New York, USA")
        assert "$" in result

    def test_mid_uk(self):
        result = _heuristic_salary(".NET Developer", "Acme", "London, UK")
        assert "£" in result

    def test_mid_gulf(self):
        result = _heuristic_salary(".NET Developer", "Acme", "Dubai, UAE")
        assert "AED" in result

    def test_senior_eu(self):
        result = _heuristic_salary("Lead Developer", "SAP", "Berlin, Germany")
        assert "€" in result

    def test_product_company_note(self):
        result = _heuristic_salary("Developer", "google", "Remote")
        assert "Product" in result or "estimated" in result.lower()

    def test_mnc_note(self):
        result = _heuristic_salary("Developer", "accenture", "Hyderabad, India")
        assert "MNC" in result or "estimated" in result.lower()

    def test_unknown_region(self):
        result = _heuristic_salary("Developer", "Acme", "Mars")
        assert "estimated" in result.lower()


class TestDetectIndianCities:
    def test_finds_bengaluru(self):
        cities = _detect_indian_cities("Office in Bengaluru and Pune")
        assert "Bengaluru" in cities
        assert "Pune" in cities

    def test_alias_bangalore(self):
        cities = _detect_indian_cities("Located in Bangalore")
        assert "Bengaluru" in cities

    def test_alias_gurgaon(self):
        cities = _detect_indian_cities("Office in Gurgaon")
        assert "Gurugram" in cities

    def test_no_cities(self):
        cities = _detect_indian_cities("Remote position, worldwide")
        assert cities == []

    def test_multiple_cities(self):
        text = "Offices in Mumbai, Chennai, Hyderabad, and Noida"
        cities = _detect_indian_cities(text)
        assert len(cities) >= 4

    def test_no_duplicates(self):
        cities = _detect_indian_cities("Bengaluru Bengaluru Bengaluru")
        assert cities.count("Bengaluru") == 1

    def test_empty_text(self):
        assert _detect_indian_cities("") == []


class TestInferSalary:
    def test_direct_salary_text(self):
        raw = RawJob("src", "1", "Dev", "Co", "Remote", "desc", "https://x.com",
                      salary_text="₹15-25 LPA")
        assert infer_salary(raw) == "₹15-25 LPA"

    def test_from_description_regex(self):
        raw = RawJob("src", "1", "Dev", "Co", "Remote",
                      "Salary: ₹12 - 20 LPA plus benefits", "https://x.com")
        result = infer_salary(raw)
        assert result != ""
        assert "12" in result

    @patch("app.enrichment._research_salary", return_value="")
    def test_heuristic_fallback(self, mock_research):
        raw = RawJob("src", "1", "Senior .NET Developer", "Acme Corp", "Bengaluru, India",
                      "Great opportunity to work with cutting edge tech", "https://x.com")
        result = infer_salary(raw)
        assert "estimated" in result.lower()

    @patch("app.enrichment._research_salary", return_value="$90K-$130K (web research)")
    def test_web_research_fallback(self, mock_research):
        raw = RawJob("src", "1", "Dev", "Co", "Remote",
                      "Join our amazing team!", "https://x.com")
        result = infer_salary(raw)
        assert "web research" in result.lower()


class TestEnrichJob:
    def test_basic_enrichment(self):
        raw = RawJob(
            source="test", external_id="1",
            title="Senior C# Developer",
            company="Microsoft",
            location="Remote, India",
            description="Looking for C# .NET Core Angular developer with Azure experience. Office in Bengaluru.",
            apply_link="https://careers.microsoft.com/123",
            salary_text="₹25-45 LPA",
        )
        enriched = enrich_job(raw)
        assert enriched.title == "Senior C# Developer"
        assert enriched.company == "Microsoft"
        assert enriched.is_mnc is True
        assert enriched.is_product_based is True
        assert "c#" in enriched.skills
        assert "Bengaluru" in enriched.indian_cities
        assert enriched.salary == "₹25-45 LPA"
        assert enriched.relevance_score > 0
        assert len(enriched.fingerprint) == 64

    def test_unknown_company(self):
        raw = RawJob("test", "1", "Dev", "SmallStartup", "Remote", "C# developer needed", "https://x.com")
        enriched = enrich_job(raw)
        assert enriched.is_mnc is False
        assert enriched.is_product_based is False

    def test_skills_capped_at_5(self):
        raw = RawJob("test", "1", ".NET Angular Developer", "Co", "Remote",
                      "C# .NET Core ASP.NET Angular Azure Docker Kubernetes SQL Server Entity Framework",
                      "https://x.com")
        enriched = enrich_job(raw)
        assert len(enriched.skills) <= 5


class TestKnownCompanySets:
    def test_mnc_set_not_empty(self):
        assert len(KNOWN_MNC) > 50

    def test_product_set_not_empty(self):
        assert len(KNOWN_PRODUCT) > 50

    def test_major_mncs_present(self):
        for company in ["microsoft", "google", "amazon", "infosys", "tcs"]:
            assert company in KNOWN_MNC, f"{company} missing from KNOWN_MNC"

    def test_major_products_present(self):
        for company in ["microsoft", "google", "atlassian", "salesforce"]:
            assert company in KNOWN_PRODUCT, f"{company} missing from KNOWN_PRODUCT"

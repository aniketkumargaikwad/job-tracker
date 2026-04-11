from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from rapidfuzz import fuzz

from app.models import RawJob

PRIMARY_SKILLS = [".net", ".net core", "c#", "microservices", "angular"]
SECONDARY_SKILLS = [
    "asp.net", "web api", "azure", "docker", "kubernetes", "sql server",
    "entity framework", "blazor", "signalr", "rabbitmq", "redis",
    "typescript", "javascript", "html", "css", "git", "ci/cd",
    "aws", "gcp", "terraform", "graphql", "grpc",
]

SKILL_SYNONYMS: dict[str, list[str]] = {
    ".net": [".net", "dotnet", "dot net", ".net framework"],
    ".net core": [".net core", ".net 5", ".net 6", ".net 7", ".net 8", ".net 9"],
    "c#": ["c#", "c-sharp", "c sharp", "csharp"],
    "microservices": ["microservice", "microservices", "distributed systems", "event driven", "event-driven"],
    "angular": ["angular", "angularjs", "angular 2", "angular 14", "angular 15", "angular 16", "angular 17"],
    "asp.net": ["asp.net", "asp net", "asp.net mvc", "asp.net core", "mvc"],
    "web api": ["web api", "rest api", "restful api", "webapi"],
    "azure": ["azure", "microsoft azure", "azure devops", "azure functions"],
    "docker": ["docker", "containers", "containerized", "containerisation"],
    "kubernetes": ["kubernetes", "k8s", "aks", "eks", "gke"],
    "sql server": ["sql server", "mssql", "t-sql", "ms sql", "transact-sql"],
    "entity framework": ["entity framework", "ef core", "ef6", "efcore"],
    "blazor": ["blazor", "blazor server", "blazor wasm"],
    "signalr": ["signalr", "signal r"],
    "rabbitmq": ["rabbitmq", "rabbit mq"],
    "redis": ["redis", "redis cache"],
    "typescript": ["typescript", "ts"],
    "javascript": ["javascript", "js", "ecmascript"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "scss", "sass"],
    "git": ["git", "github", "gitlab", "bitbucket"],
    "ci/cd": ["ci/cd", "ci cd", "cicd", "jenkins", "github actions", "azure pipelines"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud"],
    "terraform": ["terraform", "iac", "infrastructure as code"],
    "graphql": ["graphql", "graph ql"],
    "grpc": ["grpc", "g-rpc"],
}


def normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def fingerprint(job: RawJob) -> str:
    token = f"{normalize_text(job.title)}|{normalize_text(job.company)}|{normalize_text(job.apply_link)}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_likely_duplicate(job: RawJob, existing: list[tuple[str, str]]) -> bool:
    title = normalize_text(job.title)
    company = normalize_text(job.company)
    for ex_title, ex_company in existing:
        if company == normalize_text(ex_company):
            ratio = fuzz.token_set_ratio(title, normalize_text(ex_title))
            if ratio >= 90:
                return True
        similarity = SequenceMatcher(
            None,
            f"{title} {company}",
            f"{normalize_text(ex_title)} {normalize_text(ex_company)}",
        ).ratio()
        if similarity >= 0.92:
            return True
    return False


def extract_skills(description: str, title: str) -> list[str]:
    text = normalize_text(f"{title} {description}")
    scored: list[tuple[str, int]] = []
    for skill, terms in SKILL_SYNONYMS.items():
        hits = sum(1 for term in terms if term in text)
        if hits > 0:
            weight = 3 if skill in PRIMARY_SKILLS else 1
            scored.append((skill, hits * weight))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scored[:5]]


def relevance_score(description: str, title: str) -> float:
    text = normalize_text(f"{title} {description}")
    title_l = normalize_text(title)
    score = 0.0

    # Primary skills get heavy weight
    for skill in PRIMARY_SKILLS:
        for term in SKILL_SYNONYMS[skill]:
            if term in text:
                score += 16.0
                # Extra boost if skill appears in the TITLE (not just description)
                if term in title_l:
                    score += 8.0
                break

    # Secondary skills add moderate weight
    for skill in SECONDARY_SKILLS:
        for term in SKILL_SYNONYMS.get(skill, [skill]):
            if term in text:
                score += 4.0
                break

    # Location/remote bonuses
    if "remote" in text:
        score += 10
    if any(w in text for w in ("india", "global", "worldwide", "anywhere", "international")):
        score += 6
    if any(w in text for w in ("work from home", "wfh", "fully remote")):
        score += 5

    return min(score, 100.0)

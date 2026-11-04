"""Assign each free-text finding to one category from config, so types can be compared with the answer key."""

import json

from scanner.analysis import schemas
from scanner.llm.ask import ask
from scanner.llm.cache import ResponseCache
from scanner.analysis.findings import Finding, json_list
from scanner.llm.models import Model
from scanner.analysis.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from scanner.llm.usage import Usage


def classify(findings: list[Finding], classifier: Model, config: dict, cache: ResponseCache,
             usage: Usage) -> None:
    """Sets .category on each finding. The call's cost is added to `usage`."""
    if not findings:
        return
    categories = config["categories"]
    described = [{"type": f.type, "title": f.title, "explanation": f.explanation} for f in findings]
    system = CLASSIFY_SYSTEM.format(categories=json.dumps(categories))
    user = CLASSIFY_USER.format(findings=json.dumps(described, indent=2))
    labels = ask(classifier, system, user, schemas.categories(categories),
                 lambda text: parse_labels(text, len(findings), categories), cache, config, tag="classify", usage=usage)
    for finding, label in zip(findings, labels):
        finding.category = label


def parse_labels(text: str, expected: int, categories: list[str]) -> list[str]:
    labels = [label.strip().lower() for label in json_list(text, "categories", str)]
    if len(labels) != expected:
        raise ValueError(f"expected {expected} categories, got {len(labels)}")
    return [label if label in categories else "other" for label in labels]

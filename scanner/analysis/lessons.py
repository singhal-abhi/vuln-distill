"""The teacher turns its findings into general lessons, and anything app-specific is filtered out."""

import json
import re

from scanner.analysis import schemas
from scanner.llm.ask import ask
from scanner.llm.cache import ResponseCache
from scanner.analysis.findings import Finding, json_list, text_field
from scanner.llm.models import Model
from scanner.analysis.prompts import LESSONS_SYSTEM, LESSONS_USER
from scanner.llm.usage import Usage

LINE_REFERENCE = re.compile(r"\bline\s+\d+", re.IGNORECASE)


def make_lessons(teacher: Model, findings: list[Finding], identifiers: set[str],
                 config: dict, cache: ResponseCache, usage: Usage) -> tuple[list[dict], list[dict]]:
    """Single pass over the teacher's findings. Returns (general lessons, rejected lessons); the cost goes to `usage`."""
    # Without `category`: that label comes from the scoring categories, which no scanning model or lesson may see.
    shown = [{k: v for k, v in f.to_dict().items() if k != "category"} for f in findings]
    user = LESSONS_USER.format(findings=json.dumps(shown, indent=2))
    lessons = ask(teacher, LESSONS_SYSTEM, user, schemas.LESSONS, parse_lessons, cache, config, tag="lessons", usage=usage)
    kept, rejected = [], []
    for lesson in lessons:
        terms = app_specific_terms(lesson, identifiers)
        if terms:
            rejected.append({**lesson, "reason": terms})
        else:
            kept.append(lesson)
    return kept, rejected


def parse_lessons(text: str) -> list[dict]:
    lessons = [{key: text_field(lesson, key) for key in ("rule", "what_to_check", "why")}
               for lesson in json_list(text, "lessons", dict)]
    return [lesson for lesson in lessons if lesson["rule"]]   # a lesson without a rule teaches nothing


def app_specific_terms(lesson: dict, identifiers: set[str]) -> list[str]:
    """App names or line numbers a lesson mentions. Empty means the lesson is general.
    Class names match case-sensitively, so an app class "Session" rejects "Session" but not the ordinary word
    "session". All-lowercase names (the package and its last part) match in any case: "InsecureShop"."""
    text = " ".join(lesson.values())
    found = sorted(name for name in identifiers
                   if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE if name.islower() else 0))
    return found + LINE_REFERENCE.findall(text)

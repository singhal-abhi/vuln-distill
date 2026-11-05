"""The finding format every model must return, and parsing of model output into it."""

import json
import re
from dataclasses import asdict, dataclass

SEVERITIES = ["critical", "high", "medium", "low", "info"]


@dataclass
class Finding:
    type: str            # the scanning model's own words
    title: str
    file: str
    method: str
    severity: str
    evidence: str
    explanation: str
    category: str = ""   # one of config["categories"], assigned afterwards by the classifier

    def to_dict(self) -> dict:
        return asdict(self)


def parse_findings(text: str) -> list[Finding]:
    findings = []
    for item in json_list(text, "findings", dict):
        severity = text_field(item, "severity").lower()
        findings.append(Finding(
            type=text_field(item, "type"),
            title=text_field(item, "title"),
            file=clean_path(text_field(item, "file")),
            method=text_field(item, "method"),
            severity=severity if severity in SEVERITIES else "info",
            evidence=text_field(item, "evidence"),
            explanation=text_field(item, "explanation"),
        ))
    return findings


def text_field(item: dict, key: str) -> str:
    """A string field of a model reply; missing or null becomes ""."""
    value = item.get(key)
    return "" if value is None else str(value).strip()


def clean_path(path: str) -> str:
    """Models sometimes write Windows separators or a ":42" line suffix; normalise to a plain forward-slash path."""
    return re.sub(r"(:\d+)+(-\d+)?$", "", path.replace("\\", "/"))


def json_list(text: str, key: str, item_type: type) -> list:
    """The list under `key` in a model reply (a bare list is accepted too). Any other shape raises ValueError,
    so the model is asked again rather than the reply being read as "nothing found"."""
    data = extract_json(text)
    items = data.get(key) if isinstance(data, dict) else data
    if not isinstance(items, list) or not all(isinstance(item, item_type) for item in items):
        raise ValueError(f"expected a list of {item_type.__name__} under {key!r}")
    return items


def extract_json(text: str):
    """Models often wrap JSON in prose or code fences: try the reply as is, then its outermost object."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
        try:
            return json.loads(text)
        except ValueError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def merge_runs(runs: list[list[Finding]]) -> list[Finding]:
    """Every finding of the first run, plus findings from later runs at places (category, file, method) not yet
    covered, so the teacher teaches from its full coverage without repeats."""
    merged, seen = [], set()
    for findings in runs:
        new = [f for f in findings if (f.category, f.file.lower(), f.method.lower()) not in seen]
        merged += new
        seen |= {(f.category, f.file.lower(), f.method.lower()) for f in new}
    return merged

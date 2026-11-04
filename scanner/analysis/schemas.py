"""JSON schemas for every model reply. Sent to models that enforce them; the parsers still handle the rest."""

from scanner.analysis.findings import SEVERITIES


def _object(properties: dict) -> dict:
    # Strict mode (Anthropic and OpenAI) needs every field required and no extra fields.
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _array_of(item: dict) -> dict:
    return {"type": "array", "items": item}


TEXT = {"type": "string"}

FINDINGS = {
    "name": "findings",
    "schema": _object({"findings": _array_of(_object({
        "type": TEXT,
        "title": TEXT,
        "file": TEXT,
        "method": TEXT,
        "severity": {**TEXT, "enum": SEVERITIES},
        "evidence": TEXT,
        "explanation": TEXT,
    }))}),
}

LESSONS = {
    "name": "lessons",
    "schema": _object({"lessons": _array_of(_object({"rule": TEXT, "what_to_check": TEXT, "why": TEXT}))}),
}


def categories(names: list[str]) -> dict:
    return {"name": "categories", "schema": _object({"categories": _array_of({**TEXT, "enum": names})})}

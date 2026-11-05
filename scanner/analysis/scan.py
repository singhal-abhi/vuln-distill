"""Scan an app with one model, with or without lessons, then categorise the findings for scoring."""

from scanner.analysis import schemas
from scanner.llm.ask import ask
from scanner.llm.cache import ResponseCache
from scanner.llm.context import check_fits
from scanner.analysis.classify import classify
from scanner.analysis.findings import SEVERITIES, Finding, parse_findings
from scanner.ingest.app import App
from scanner.llm.models import Model
from scanner.analysis.prompts import scan_system, scan_user
from scanner.llm.usage import Usage


def scan(model: Model, app: App, config: dict, cache: ResponseCache, tag: str, classifier: Model,
         lessons: list[dict] | None = None) -> tuple[list[Finding], Usage]:
    """`tag` (role and run number) keeps repeated runs, and teacher vs. student runs of one model, separate in the cache.
    Returns the findings and what the run cost: the scan plus classifying its findings."""
    usage = Usage()
    system, user = scan_prompt(app, lessons)
    check_fits(model, system, user, config)   # the exact prompt, lessons included; pipeline.run checks before any call
    findings = ask(model, system, user, schemas.FINDINGS, parse_findings, cache, config, tag=tag, usage=usage)
    classify(findings, classifier, config, cache, usage)
    return findings, usage


def scan_prompt(app: App, lessons: list[dict] | None = None) -> tuple[str, str]:
    """(system, user) prompts for one scan."""
    return scan_system(SEVERITIES), scan_user(app.to_prompt(), lessons)

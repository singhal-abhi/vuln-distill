"""What gets saved in the work dir: findings and their cost per model and condition, and the teacher's lessons."""

import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from scanner.analysis.findings import Finding
from scanner.llm.usage import Usage

# Conditions findings are saved under. The teacher has its own, so a student that is the same model can't overwrite it.
TEACHER, BASELINE, WITH_LESSONS = "teacher", "baseline", "lessons"
LESSONS_FILE = "lessons.json"
USAGE_FILE = "usage.json"   # per folder: what each run cost, in run order


def findings_folder(work_dir: Path, model: str, condition: str) -> Path:
    """e.g. findings/openrouter_google_gemma-4-26b-a4b-it_free/baseline: the model id made safe as a folder name."""
    return work_dir / "findings" / re.sub(r"[^\w.-]+", "_", model) / condition


def save_findings(work_dir: Path, model: str, condition: str, runs: list[list[Finding]],
                  usages: list[Usage]) -> None:
    folder = findings_folder(work_dir, model, condition)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("run-*.json"):   # a smaller run count must not leave stale runs behind
        old.unlink()
    for run, findings in enumerate(runs, 1):
        _write(folder / f"run-{run}.json", [f.to_dict() for f in findings])
    _write(folder / USAGE_FILE, [asdict(usage) for usage in usages])


def _write(path: Path, data) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2))
    os.replace(temp, path)   # atomic: an interrupted run never leaves a broken file


def load_runs(work_dir: Path, model: str, condition: str) -> list[list[Finding]]:
    """[findings of run 1, run 2, ...]; empty if nothing is saved. Files are only ever written by save_findings,
    so a file that doesn't fit Finding means the code changed since: that fails loudly (re-run with --force)."""
    paths = findings_folder(work_dir, model, condition).glob("run-*.json")
    return [[Finding(**item) for item in json.loads(path.read_text())]
            for path in sorted(paths, key=lambda p: int(p.stem.split("-")[1]))]


def load_usage(work_dir: Path, model: str, condition: str) -> list[Usage]:
    """What each saved run cost; empty if not recorded."""
    try:
        return [Usage(**usage) for usage in json.loads((findings_folder(work_dir, model, condition) / USAGE_FILE).read_text())]
    except (OSError, ValueError, TypeError):
        return []


def save_lessons(work_dir: Path, teacher: str, lessons: list[dict], rejected: list[dict], usage: Usage) -> None:
    _write(work_dir / LESSONS_FILE, {"teacher": teacher, "lessons": lessons, "rejected": rejected, "usage": asdict(usage)})


def read_lessons(work_dir: Path) -> dict | None:
    """The saved lessons file, or None if it is missing or unreadable."""
    try:
        saved = json.loads((work_dir / LESSONS_FILE).read_text())
    except (OSError, ValueError):
        return None
    return saved if isinstance(saved, dict) else None

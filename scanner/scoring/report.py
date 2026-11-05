"""Score saved findings and write a short, fixed-layout report. Makes no model calls.

What is scored: each student's findings without vs with lessons, against a reference:
- the app's answer key when it has one: recall, the share of known vulnerabilities found;
- otherwise the teacher's findings: agreement, the share of the teacher's findings the student also found. This needs
  no human labels, so it works on any app, but the teacher misses bugs and can be wrong, so it is not true recall.
"""

import json
from dataclasses import asdict
from pathlib import Path
from statistics import mean

from scanner.analysis.findings import merge_runs
from scanner.config import resolve
from scanner.llm.usage import Usage, total
from scanner.scoring.match import Vulnerability, load_ground_truth, match_findings, teacher_reference
from scanner.store import BASELINE, TEACHER, WITH_LESSONS, load_runs, load_usage, read_lessons


def write_report(config: dict) -> str | None:
    """Writes report.md and scores.json and returns the report; None if there is nothing to score against yet
    (no answer key and no saved teacher scan)."""
    work_dir = resolve(config, config["app"]["work_dir"])
    reference, by_teacher = _reference(config, work_dir)
    if not reference:
        return None
    location_mode = config["match"]["location"]
    measure = "Agreement" if by_teacher else "Recall"

    rows = _rows(config)
    scores = {}   # (model, condition) -> per-run numbers
    for _, model, condition in rows:
        if by_teacher and condition == TEACHER:
            continue   # the teacher is the reference here; scoring it against itself would always give 100%
        runs = load_runs(work_dir, model, condition)
        if runs:
            matches = [match_findings(findings, reference, location_mode) for findings in runs]
            scores[(model, condition)] = {
                "recall": [len(m) / len(reference) for m in matches],
                "findings": [len(findings) for findings in runs],
                "unmatched": [len(findings) - len(m) for findings, m in zip(runs, matches)],
                "hits": {v.id: sum(v.id in m for m in matches) for v in reference},
                "usage": load_usage(work_dir, model, condition),
            }
    shown = [row for row in rows if (row[1], row[2]) in scores]
    teacher_usage = load_usage(work_dir, config["teacher"], TEACHER) if by_teacher else []
    lessons = read_lessons(work_dir)

    if by_teacher:
        intro = (f"No answer key, so the students are scored against the teacher's {len(reference)} findings. A student "
                 f"finding counts when its bug type and {location_mode} match one of the teacher's. This is agreement "
                 "with the teacher, not true recall: the teacher misses some bugs, and some of its findings may be wrong.")
    else:
        intro = f"{len(reference)} known vulnerabilities. A finding counts when its bug type and {location_mode} match the answer key."
    lines = ["# Results", "", intro, "",
             "**Models:** " + " · ".join(f"{label} `{model}`" for label, model, condition in rows if condition != WITH_LESSONS)
             + f" · Classifier `{config['classifier']}`", ""]
    teacher_scores = scores.get((config["teacher"], TEACHER))
    lines += _lift_lines(config, rows, scores, 1.0 if by_teacher else teacher_scores and mean(teacher_scores["recall"]))

    if shown:
        lines += ["", "```mermaid", "xychart-beta", f'    title "{measure}: mean over runs (%)"',
                  "    x-axis [" + ", ".join(f'"{label}"' for label, _, _ in shown) + "]",
                  f'    y-axis "{measure} (%)" 0 --> 100',
                  "    bar [" + ", ".join(f"{mean(scores[(m, c)]['recall']) * 100:.0f}" for _, m, c in shown) + "]",
                  "```"]

    lines += ["", f"| | {measure} | Range | Runs | Findings / run | Unmatched / run | Cost / run |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for label, model, condition in rows:
        s = scores.get((model, condition))
        if by_teacher and condition == TEACHER:
            lines.append(f"| {label} | the reference | | | {len(reference)} findings | | {_cost(teacher_usage)} |")
        elif not s:
            lines.append(f"| {label} | not run | | | | | |")
        else:
            low, high = min(s["recall"]), max(s["recall"])
            spread = f"{low:.0%}" if low == high else f"{low:.0%}–{high:.0%}"
            lines.append(f"| {label} | **{mean(s['recall']):.0%}** | {spread} | {len(s['recall'])} "
                         f"| {mean(s['findings']):.1f} | {mean(s['unmatched']):.1f} | {_cost(s['usage'])} |")

    # Cost to produce each result (a run's scan plus classifying its findings), even if it was served from the cache now.
    runs_usage = [usage for s in scores.values() for usage in s["usage"]] + teacher_usage
    if runs_usage:
        lessons_usage = [Usage(**lessons["usage"])] if lessons and "usage" in lessons else []
        spent = runs_usage + lessons_usage
        lessons_note = f" Writing the lessons: {_money(lessons_usage[0].cost)}." if lessons_usage else ""
        lines += ["", f"**Total cost: {_money(total(spent).cost)}** ({_tokens(spent, per_run=False)} tokens). "
                      f"Each run includes classifying its findings.{lessons_note}"]

    if shown:
        lines += ["", "## Per teacher finding" if by_teacher else "## Per vulnerability", "",
                  "Each dot is one run: ● found, ○ missed. ▲ / ▼: found in more / fewer runs with lessons.", "",
                  f"| # | {'Teacher finding' if by_teacher else 'Vulnerability'} | " + " | ".join(label for label, _, _ in shown) + " |",
                  "|---:|---|" + ":---:|" * len(shown)]
        for v in reference:
            cells = [_dots(scores, model, condition, v.id) for _, model, condition in shown]
            lines.append(f"| {v.id} | {v.name} | " + " | ".join(cells) + " |")

    if lessons and lessons.get("lessons"):
        lines += ["", f"## Lessons given to the students ({len(lessons['lessons'])}, "
                      f"{len(lessons.get('rejected', []))} rejected as app-specific)", ""]
        lines += [f"{i}. {lesson['rule']}" for i, lesson in enumerate(lessons["lessons"], 1)]

    report = "\n".join(lines) + "\n"
    work_dir.mkdir(parents=True, exist_ok=True)   # `report` may run before anything was scanned
    (work_dir / "report.md").write_text(report)
    saved = {f"{m}/{c}": {**s, "usage": [asdict(u) for u in s["usage"]]} for (m, c), s in scores.items()}
    (work_dir / "scores.json").write_text(json.dumps({"reference": "teacher" if by_teacher else "answer key",
                                                      "measure": measure.lower(), "scores": saved}, indent=2))
    return report


def _reference(config: dict, work_dir: Path) -> tuple[list[Vulnerability] | None, bool]:
    """(reference entries, whether they are the teacher's findings): the answer key when the app has one, otherwise
    the teacher's saved findings (all its runs merged), otherwise None."""
    ground_truth = config["app"].get("ground_truth")
    if ground_truth and resolve(config, ground_truth).is_file():
        return load_ground_truth(resolve(config, ground_truth)), False
    teacher_runs = load_runs(work_dir, config["teacher"], TEACHER)
    return (teacher_reference(merge_runs(teacher_runs)) if teacher_runs else None), True


def _rows(config: dict) -> list[tuple[str, str, str]]:
    """(label, model, condition) for every row, in report order: what is scored (each student without and with
    lessons) first, the teacher last as a reference. Students are numbered only when there are several."""
    rows = []
    for n, student in enumerate(config["students"], 1):
        name = f"Student {n}" if len(config["students"]) > 1 else "Student"
        rows += [(name, student, BASELINE), (f"{name} + lessons", student, WITH_LESSONS)]
    return rows + [("Teacher (reference)", config["teacher"], TEACHER)]


def _lift_lines(config: dict, rows: list[tuple[str, str, str]], scores: dict, teacher: float | None) -> list[str]:
    """One line per student: its lift from lessons and, when the teacher's score is known, how much of the gap to
    the teacher it closes. Against the teacher's own findings, the teacher scores 100% by definition."""
    lines = []
    for label, student, condition in rows:
        before, after = scores.get((student, BASELINE)), scores.get((student, WITH_LESSONS))
        if condition != BASELINE or not (before and after):
            continue
        b, a = mean(before["recall"]), mean(after["recall"])
        gap = f"; closes {(a - b) / (teacher - b):.0%} of the gap to the teacher" if teacher and teacher > b else ""
        who = f" ({label})" if len(config["students"]) > 1 else ""
        lines.append(f"**Lift from lessons{who}: {(a - b) * 100:+.0f} points** ({b:.0%} → {a:.0%}{gap})")
    return lines


def _dots(scores: dict, model: str, condition: str, vuln_id: int) -> str:
    """e.g. "●●○" for found in 2 of 3 runs, with ▲ / ▼ on a with-lessons cell that differs from the baseline."""
    s = scores[(model, condition)]
    runs, hits = len(s["recall"]), s["hits"][vuln_id]
    dots = "●" * hits + "○" * (runs - hits)
    before = scores.get((model, BASELINE))
    if condition == WITH_LESSONS and before:
        change = hits / runs - before["hits"][vuln_id] / len(before["recall"])
        dots += " ▲" if change > 0 else " ▼" if change < 0 else ""
    return dots


def _money(cost: float | None) -> str:
    if cost is None:
        return "unknown"
    return f"${cost:.4f}" if 0 < cost < 0.01 else f"${cost:.2f}"   # sub-cent costs (e.g. the classifier) stay visible


def _cost(usages: list[Usage]) -> str:
    """Mean cost per run; blank if the runs were saved before cost was recorded."""
    if not usages:
        return ""
    cost = total(usages).cost
    return _money(None if cost is None else cost / len(usages))


def _tokens(usages: list[Usage], per_run: bool = True) -> str:
    """e.g. "41.2k in / 2.3k out", averaged per run unless per_run is False."""
    if not usages:
        return ""
    summed, runs = total(usages), (len(usages) if per_run else 1)
    return f"{summed.input_tokens / runs / 1000:.1f}k in / {summed.output_tokens / runs / 1000:.1f}k out"

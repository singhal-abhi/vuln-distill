"""Score saved findings against the answer key and write a short, fixed-layout report. Makes no model calls.

Always the same rows, in order: the teacher, then each student without and with lessons.
"""

import json
from dataclasses import asdict
from statistics import mean

from scanner.config import resolve
from scanner.scoring.match import load_ground_truth, match_findings
from scanner.store import BASELINE, TEACHER, WITH_LESSONS, load_runs, load_usage, read_lessons
from scanner.llm.usage import Usage, total


def write_report(config: dict) -> str:
    work_dir = resolve(config, config["app"]["work_dir"])
    answer_key = load_ground_truth(resolve(config, config["app"]["ground_truth"]))
    location_mode = config["match"]["location"]

    rows = _rows(config)
    scores = {}   # (model, condition) -> per-run numbers
    for _, model, condition in rows:
        runs = load_runs(work_dir, model, condition)
        if runs:
            matches = [match_findings(findings, answer_key, location_mode) for findings in runs]
            scores[(model, condition)] = {
                "recall": [len(m) / len(answer_key) for m in matches],
                "findings": [len(findings) for findings in runs],
                "unmatched": [len(findings) - len(m) for findings, m in zip(runs, matches)],
                "hits": {v.id: sum(v.id in m for m in matches) for v in answer_key},
                "usage": load_usage(work_dir, model, condition),
            }
    shown = [row for row in rows if (row[1], row[2]) in scores]
    lessons = read_lessons(work_dir)

    lines = ["# Results", "",
             f"{len(answer_key)} known vulnerabilities. A finding counts when its bug type and {location_mode} match "
             "the answer key.", "",
             "**Models:** " + " · ".join(f"{label} `{model}`" for label, model, condition in rows if condition != WITH_LESSONS)
             + f" · Classifier `{config['classifier']}`", ""]
    lines += _lift_lines(config, rows, scores)

    if shown:
        lines += ["", "```mermaid", "xychart-beta", '    title "Recall: mean over runs (%)"',
                  "    x-axis [" + ", ".join(f'"{label}"' for label, _, _ in shown) + "]",
                  '    y-axis "Recall (%)" 0 --> 100',
                  "    bar [" + ", ".join(f"{mean(scores[(m, c)]['recall']) * 100:.0f}" for _, m, c in shown) + "]",
                  "```"]

    lines += ["", "| | Recall | Range | Runs | Findings / run | Unmatched / run | Cost / run |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for label, model, condition in rows:
        s = scores.get((model, condition))
        if not s:
            lines.append(f"| {label} | not run | | | | | |")
            continue
        low, high = min(s["recall"]), max(s["recall"])
        spread = f"{low:.0%}" if low == high else f"{low:.0%}–{high:.0%}"
        lines.append(f"| {label} | **{mean(s['recall']):.0%}** | {spread} | {len(s['recall'])} "
                     f"| {mean(s['findings']):.1f} | {mean(s['unmatched']):.1f} | {_cost(s['usage'])} |")

    # Cost to produce each result (a run's scan plus classifying its findings), even if it was served from the cache now.
    runs_usage = [usage for s in scores.values() for usage in s["usage"]]
    if runs_usage:
        lessons_usage = [Usage(**lessons["usage"])] if lessons and "usage" in lessons else []
        spent = runs_usage + lessons_usage
        lessons_note = f" Writing the lessons: {_money(lessons_usage[0].cost)}." if lessons_usage else ""
        lines += ["", f"**Total cost: {_money(total(spent).cost)}** ({_tokens(spent, per_run=False)} tokens). "
                      f"Each run includes classifying its findings.{lessons_note}"]

    if shown:
        lines += ["", "## Per vulnerability", "",
                  "Each dot is one run: ● found, ○ missed. ▲ / ▼: found in more / fewer runs with lessons.", "",
                  "| # | Vulnerability | " + " | ".join(label for label, _, _ in shown) + " |",
                  "|---:|---|" + ":---:|" * len(shown)]
        for v in answer_key:
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
    (work_dir / "scores.json").write_text(json.dumps(saved, indent=2))
    return report


def _rows(config: dict) -> list[tuple[str, str, str]]:
    """(label, model, condition) for every row, in report order. Students are numbered only when there are several."""
    rows = [("Teacher", config["teacher"], TEACHER)]
    for n, student in enumerate(config["students"], 1):
        name = f"Student {n}" if len(config["students"]) > 1 else "Student"
        rows += [(name, student, BASELINE), (f"{name} + lessons", student, WITH_LESSONS)]
    return rows


def _lift_lines(config: dict, rows: list[tuple[str, str, str]], scores: dict) -> list[str]:
    teacher = scores.get((config["teacher"], TEACHER))
    lines = []
    for label, student, condition in rows:
        before, after = scores.get((student, BASELINE)), scores.get((student, WITH_LESSONS))
        if condition != BASELINE or not (before and after):
            continue
        b, a = mean(before["recall"]), mean(after["recall"])
        gap = f"; closes {(a - b) / (mean(teacher['recall']) - b):.0%} of the gap to the teacher" \
            if teacher and mean(teacher["recall"]) > b else ""
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

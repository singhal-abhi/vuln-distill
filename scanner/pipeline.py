"""The loop as three steps: teacher (once) -> students without lessons -> students with lessons."""

from pathlib import Path

from scanner.llm.cache import ResponseCache
from scanner.config import resolve
from scanner.analysis.findings import Finding, merge_runs
from scanner.ingest.app import load_app
from scanner.analysis.lessons import make_lessons
from scanner.llm.models import build_model
from scanner.analysis.scan import scan, scan_prompt
from scanner.llm.context import check_fits
from scanner.store import BASELINE, TEACHER, WITH_LESSONS, load_runs, read_lessons, save_findings, save_lessons
from scanner.llm.usage import Usage, total

STUDENT_STEPS = {"student": BASELINE, "student-lessons": WITH_LESSONS}   # step name -> condition it saves
STEPS = ["teacher", *STUDENT_STEPS]


def run(config: dict, steps: list[str], force_teacher: bool = False) -> None:
    work_dir = resolve(config, config["app"]["work_dir"])
    teacher_needed = "teacher" in steps and (force_teacher or not ready_lessons(work_dir, config))
    conditions = [STUDENT_STEPS[step] for step in steps if step in STUDENT_STEPS]
    if "teacher" in steps and not teacher_needed:
        print(f"Teacher {config['teacher']}: already done, reusing saved findings and lessons (--force to redo)")
    if WITH_LESSONS in conditions and not teacher_needed:
        load_lessons(work_dir, config)   # fail now, before decompiling or building any model
    if not teacher_needed and not conditions:
        return

    app = load_app(config)
    classifier = build_model(config, config["classifier"])
    # Build every model and check the app fits each one before any call, so a too-small student stops the run
    # before the teacher spends anything. scan() checks again with the exact prompt, lessons included.
    teacher = build_model(config, config["teacher"]) if teacher_needed else None
    students = [build_model(config, name) for name in config["students"]] if conditions else []
    system, user = scan_prompt(app, ready_lessons(work_dir, config) or None)
    for model in filter(None, [teacher, *students]):
        check_fits(model, system, user, config)
    if teacher:
        run_teacher(config, app, work_dir, teacher, classifier, force_teacher)
    lessons = ready_lessons(work_dir, config)
    if WITH_LESSONS in conditions and not lessons:
        # The teacher just ran but left no usable lessons (all rejected, say). Without lessons the "with lessons"
        # prompt would just replay the baseline, so skip it; the baseline still runs.
        print(f"Teacher {config['teacher']} left no usable lessons (see lessons.json): skipping the with-lessons scans. "
              "Run --step teacher to try again.")
        conditions.remove(WITH_LESSONS)
    if not conditions:   # e.g. --step teacher: don't build student clients (their API keys may not be set)
        return

    cache = response_cache(config)
    for student in students:
        for condition in conditions:
            condition_lessons = lessons if condition == WITH_LESSONS else None
            print(f"Student {student.name}: scanning " + (f"with {len(lessons)} lessons" if condition_lessons else "without lessons"))
            runs, usages = scan_runs(student, app, config, cache, condition, classifier,
                                     config["run"]["student_runs"], condition_lessons)
            save_findings(work_dir, student.name, condition, runs, usages)


def scan_runs(model, app, config: dict, cache: ResponseCache, condition: str, classifier, count: int,
              lessons: list[dict] | None = None) -> tuple[list[list[Finding]], list[Usage]]:
    """`count` scans, each logged with its findings and cost. A cached run shows what it cost when first run.

    The runs are independent (each has its own cache tag) and could all run at once, as could the students and
    conditions in `run`. They run one after another on purpose, so free-tier rate limits are not hit; the retries in
    `complete_with_retries` absorb the occasional limit that still is.
    """
    runs, usages = [], []
    for run in range(1, count + 1):
        findings, usage = scan(model, app, config, cache, f"{condition}-run-{run}", classifier, lessons)
        print(f"  run {run}: {len(findings)} findings, {usage}")
        runs.append(findings)
        usages.append(usage)
    if count > 1:
        print(f"  total: {total(usages)}")
    return runs, usages


def run_teacher(config: dict, app, work_dir: Path, teacher, classifier, force: bool) -> None:
    """Two stages saved separately: the scan, then the lessons. Saved findings are always reused (even if
    teacher_runs changed since); only --force scans again, with fresh calls rather than cached replies."""
    saved = load_runs(work_dir, teacher.name, TEACHER)
    if saved and not force:
        print(f"Teacher {teacher.name}: reusing saved scan ({len(saved)} run(s))")
        runs = saved
    else:
        print(f"Teacher {teacher.name}: scanning")
        cache = response_cache(config, refresh=force)
        runs, usages = scan_runs(teacher, app, config, cache, TEACHER, classifier, config["run"]["teacher_runs"])
        save_findings(work_dir, teacher.name, TEACHER, runs, usages)

    findings = merge_runs(runs)
    if not findings:
        raise SystemExit(f"Teacher {teacher.name} found nothing, so there is nothing to teach. Re-run with --force.")
    print(f"Teacher {teacher.name}: writing lessons")
    # This only runs when lessons are missing or empty, so always ask afresh: a cached reply would give the same lessons.
    fresh = response_cache(config, refresh=True)
    usage = Usage()
    lessons, rejected = make_lessons(teacher, findings, app.identifiers(), config, fresh, usage)
    save_lessons(work_dir, teacher.name, lessons, rejected, usage)
    print(f"  {len(lessons)} lessons kept, {len(rejected)} rejected as app-specific; {usage}")


def response_cache(config: dict, refresh: bool = False) -> ResponseCache:
    return ResponseCache(resolve(config, config["cache_dir"]), refresh=refresh)


def ready_lessons(work_dir: Path, config: dict) -> list[dict]:
    """The configured teacher's saved lessons; empty if missing, empty, or from another teacher. Empty means the
    teacher step runs again (reusing its saved scan). To redo the lessons on purpose, delete lessons.json."""
    saved = read_lessons(work_dir) or {}
    if saved.get("teacher") != config["teacher"]:
        return []
    return saved.get("lessons") or []


def load_lessons(work_dir: Path, config: dict) -> list[dict]:
    lessons = ready_lessons(work_dir, config)
    if not lessons:
        raise SystemExit(f"No lessons from teacher {config['teacher']} yet. Run: python -m scanner run --step teacher")
    return lessons


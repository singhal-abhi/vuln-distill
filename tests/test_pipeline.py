import json

from scanner.analysis.findings import Finding
from scanner.analysis.findings import merge_runs
from scanner.pipeline import ready_lessons
from scanner.store import findings_folder, load_runs, load_usage, save_findings
from scanner.llm.usage import Usage

CONFIG = {"teacher": "t"}


def test_ready_lessons(tmp_path):
    assert ready_lessons(tmp_path, CONFIG) == []                       # missing
    path = tmp_path / "lessons.json"
    for content in ["", "[]", '{"teacher": "t", "lessons": []}', '{"teacher": "other", "lessons": [{"rule": "R"}]}']:
        path.write_text(content)
        assert ready_lessons(tmp_path, CONFIG) == [], content         # unreadable, wrong shape, empty, other teacher
    path.write_text(json.dumps({"teacher": "t", "lessons": [{"rule": "R"}]}))
    assert ready_lessons(tmp_path, CONFIG) == [{"rule": "R"}]


def finding(title, file="A.java", category="c"):
    return Finding(type="t", title=title, file=file, method="", severity="high", evidence="", explanation="", category=category)


def test_merge_keeps_distinct_findings_of_one_run_and_adds_only_new_places():
    run1 = [finding("secret 1"), finding("secret 2")]
    run2 = [finding("secret 1 again"), finding("other", file="B.java")]
    assert [f.title for f in merge_runs([run1, run2])] == ["secret 1", "secret 2", "other"]


def test_findings_and_cost_round_trip_under_a_full_model_id(tmp_path):
    model = "openrouter/google/gemma-4-26b-a4b-it:free"
    save_findings(tmp_path, model, "baseline", [[finding("x")], [finding("y")]], [Usage(5, 1, 0.25), Usage()])
    assert findings_folder(tmp_path, model, "baseline").parent.name == "openrouter_google_gemma-4-26b-a4b-it_free"
    assert [[f.title for f in run] for run in load_runs(tmp_path, model, "baseline")] == [["x"], ["y"]]
    assert load_usage(tmp_path, model, "baseline") == [Usage(5, 1, 0.25), Usage()]   # usage.json is not a run
    assert load_runs(tmp_path, model, "lessons") == [] and load_usage(tmp_path, model, "lessons") == []


def test_lessons_prompt_hides_categories(monkeypatch):
    from scanner.analysis import lessons
    seen = {}
    monkeypatch.setattr(lessons, "ask", lambda model, system, user, *a, **k: seen.setdefault("user", user) and [])
    lessons.make_lessons(None, [finding("x", category="insecure-webview")], set(), {}, None, Usage())
    assert "insecure-webview" not in seen["user"] and '"title": "x"' in seen["user"]


def test_without_answer_key_students_are_scored_against_the_teacher(tmp_path):
    from scanner.scoring.report import write_report
    config = {"root": tmp_path, "app": {"work_dir": "work"}, "match": {"location": "file"},
              "teacher": "t", "students": ["s"], "classifier": "c"}
    work = tmp_path / "work"
    assert write_report(config) is None   # nothing to score against yet
    teacher = [finding("a", file="A.java"), finding("b", file="B.java")]
    save_findings(work, "t", "teacher", [teacher], [Usage()])
    save_findings(work, "s", "baseline", [[finding("a", file="A.java")]], [Usage()])
    save_findings(work, "s", "lessons", [[finding("a", file="A.java"), finding("b", file="B.java")]], [Usage()])
    report = write_report(config)
    assert "scored against the teacher's 2 findings" in report and "+50 points" in report
    assert "| Teacher (reference) | the reference |" in report   # the teacher is not scored against itself
    saved = json.loads((work / "scores.json").read_text())
    assert saved["reference"] == "teacher" and saved["scores"]["s/lessons"]["recall"] == [1.0]


def test_several_students_each_run_both_conditions_with_the_same_lessons(tmp_path, monkeypatch):
    """The real pipeline and report with two students and fake models: no API calls."""
    from scanner import pipeline
    from scanner.llm.models import Reply
    from scanner.scoring.report import write_report

    prompts_seen = {}   # (model, kind) -> user prompts

    class FakeModel:
        def __init__(self, name):
            self.name = name

        def complete(self, system, user, schema=None):
            if system.startswith("You sort security findings"):          # classifier
                count = len(json.loads(user.split("Findings:\n\n", 1)[1]))
                text = json.dumps({"categories": ["insecure-webview"] * count})
            elif "training a junior reviewer" in system:                  # teacher's lessons
                text = json.dumps({"lessons": [{"rule": "Check WebView settings", "what_to_check": "x", "why": "y"}]})
            else:                                                         # a scan
                kind = "lessons" if "A good pentester" in user else "scan"
                prompts_seen.setdefault((self.name, kind), []).append(user)
                files = {"t": ["A.java", "B.java"], "s1": ["A.java"], "s2": []}[self.name]
                if kind == "lessons":
                    files = ["A.java", "B.java"]                          # both students improve with lessons
                text = json.dumps({"findings": [{"type": "webview", "title": f, "file": f} for f in files]})
            return Reply(text, Usage(10, 1, 0.0))

    class FakeApp:
        def to_prompt(self):
            return "### FILE: A.java\n...\n### FILE: B.java\n..."

        def identifiers(self):
            return {"AppSpecificClass"}

    monkeypatch.setattr(pipeline, "build_model", lambda config, name: FakeModel(name))
    monkeypatch.setattr(pipeline, "load_app", lambda config: FakeApp())
    config = {"root": tmp_path, "app": {"work_dir": "work"}, "cache_dir": "cache", "match": {"location": "file"},
              "teacher": "t", "students": ["s1", "s2"], "classifier": "c", "categories": ["insecure-webview", "other"],
              "run": {"teacher_runs": 1, "student_runs": 2, "max_retries": 0, "parse_retries": 0}}

    pipeline.run(config, pipeline.STEPS)

    work = tmp_path / "work"
    for student in ["s1", "s2"]:
        for condition in ["baseline", "lessons"]:
            assert len(load_runs(work, student, condition)) == 2, (student, condition)   # saved separately
    # Both students got the very same lessons text in their with-lessons prompts.
    assert prompts_seen[("s1", "lessons")][0] == prompts_seen[("s2", "lessons")][0]
    assert "Check WebView settings" in prompts_seen[("s1", "lessons")][0]

    report = write_report(config)   # no ground truth: scored against the teacher's two findings
    for row in ["| Student 1 |", "| Student 1 + lessons |", "| Student 2 |", "| Student 2 + lessons |", "| Teacher (reference) |"]:
        assert row in report, row
    assert "Lift from lessons (Student 1): +50 points" in report     # 1 of 2 -> 2 of 2
    assert "Lift from lessons (Student 2): +100 points" in report    # 0 of 2 -> 2 of 2
    assert "\n\n**Lift from lessons (Student 2)" in report             # its own paragraph, not merged with Student 1's

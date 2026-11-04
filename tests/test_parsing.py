import pytest

from scanner.analysis.classify import parse_labels
from scanner.analysis.findings import parse_findings
from scanner.ingest.app import App
from scanner.analysis.lessons import app_specific_terms, parse_lessons
from scanner.analysis.prompts import scan_system, scan_user

CATEGORIES = ["insecure-webview", "other"]


def test_parses_fenced_json_with_prose_around_it():
    text = 'Here you go:\n```json\n{"findings": [{"type": "WebView issue", "file": "A.java"}]}\n```\nDone.'
    [f] = parse_findings(text)
    assert (f.type, f.file, f.severity, f.category) == ("WebView issue", "A.java", "info", "")


def test_garbage_raises_value_error():
    with pytest.raises(ValueError):
        parse_findings("no json here")


def test_classifier_labels_unknown_become_other():
    assert parse_labels('{"categories": ["insecure-webview", "made-up"]}', 2, CATEGORIES) == ["insecure-webview", "other"]


def test_classifier_label_count_must_match():
    with pytest.raises(ValueError):
        parse_labels('{"categories": ["insecure-webview"]}', 2, CATEGORIES)


def test_lessons_only_change_the_user_message():
    lessons = [{"rule": "R", "what_to_check": "W", "why": "Y"}]
    assert scan_user("APP", None) in scan_user("APP", lessons)
    assert "at least these points" in scan_user("APP", lessons)
    assert "webview" not in scan_system(["high"]).lower()   # the scan prompt names no bug types


def test_general_lesson_passes():
    [lesson] = parse_lessons('{"lessons": [{"rule": "Exported activities that forward intent extras are risky",'
                             ' "what_to_check": "getParcelableExtra then startActivity", "why": "intent redirection"}]}')
    assert app_specific_terms(lesson, {"WebViewActivity", "com.insecureshop"}) == []


def test_lesson_naming_app_class_or_line_is_rejected():
    lesson = {"rule": "Check WebViewActivity on line 12", "what_to_check": "", "why": ""}
    assert app_specific_terms(lesson, {"WebViewActivity"}) == ["WebViewActivity", "line 12"]


@pytest.mark.parametrize("reply", ['{"findings": null}', '{"findings": ["x"]}', '{"findings": {"a": 1}}',
                                   '[{"type": "x"}, ]', '{"other": []}'])
def test_wrong_reply_shapes_raise_value_error_so_they_are_re_asked(reply):
    with pytest.raises(ValueError):
        parse_findings(reply)


def test_bare_list_and_null_fields():
    [f] = parse_findings('[{"type": null, "file": "com\\\\x\\\\Util.java:42", "severity": "HIGH"}]')
    assert (f.type, f.file, f.severity) == ("", "com/x/Util.java", "high")


def test_lessons_without_a_rule_are_dropped():
    assert parse_lessons('{"lessons": [{"rule": null}, {}, {"rule": "R"}]}') == [{"rule": "R", "what_to_check": "", "why": ""}]


def test_app_identifier_match_is_case_sensitive():
    lesson = {"rule": "Session tokens in a session store", "what_to_check": "", "why": ""}
    assert app_specific_terms(lesson, {"session"}) == ["session"]
    assert app_specific_terms({"rule": "Check each session", "what_to_check": "", "why": ""}, {"Session"}) == []


def test_code_fences_inside_json_strings_are_fine():
    [f] = parse_findings('{"findings": [{"evidence": "use ```x``` here", "file": "A.java:10:5"}]}')
    assert (f.evidence, f.file) == ("use ```x``` here", "A.java")


def test_app_short_name_is_caught_in_any_case():
    lesson = {"rule": "InsecureShop stores passwords", "what_to_check": "", "why": ""}
    assert app_specific_terms(lesson, {"insecureshop"}) == ["insecureshop"]


def test_build_generated_classes_are_not_app_specific():
    app = App("com.example.shop", "", {"com/example/shop/BuildConfig.java": "", "com/example/shop/CartActivity.java": ""},
              {"res/xml/network_security_config.xml": ""}, [])
    names = app.identifiers()
    assert "CartActivity" in names and "BuildConfig" not in names and "network_security_config" not in names
    lesson = {"rule": "Never put secrets in BuildConfig fields", "what_to_check": "", "why": ""}
    assert app_specific_terms(lesson, names) == []


def test_lessons_prompt_asks_for_general_lessons_only():
    from scanner.analysis.prompts import LESSONS_SYSTEM
    for rule in ["ANY Android app", "Never mention this app's", "Never describe the app you saw"]:
        assert rule in LESSONS_SYSTEM

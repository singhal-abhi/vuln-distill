from scanner.analysis.findings import Finding
from scanner.scoring.match import Location, Vulnerability, is_match, match_findings


def finding(category, file, method=""):
    return Finding(type="t", title="t", file=file, method=method, severity="high",
                   evidence="e", explanation="x", category=category)


WEBVIEW = Vulnerability(17, "WebView", ["insecure-webview"], [Location("com/app/WebViewActivity.java", "onCreate")])


def test_needs_right_type_and_right_file():
    assert is_match(finding("insecure-webview", "com/app/WebViewActivity.java"), WEBVIEW, "file")
    assert not is_match(finding("insecure-logging", "com/app/WebViewActivity.java"), WEBVIEW, "file")
    assert not is_match(finding("insecure-webview", "com/app/Other.java"), WEBVIEW, "file")


def test_bare_file_name_matches_full_path():
    assert is_match(finding("insecure-webview", "WebViewActivity.java"), WEBVIEW, "file")
    assert not is_match(finding("insecure-webview", "MyWebViewActivity.java"), WEBVIEW, "file")


def test_path_written_package_style_or_with_several_files_still_matches():
    web = Vulnerability(1, "W", ["insecure-webview"], [Location("com/app/ui/WebViewActivity.java")])
    assert is_match(finding("insecure-webview", "com/app.ui/WebViewActivity.java"), web, "file")
    assert is_match(finding("insecure-webview", "com.app.ui.WebViewActivity.java"), web, "file")
    assert is_match(finding("insecure-webview", "AndroidManifest.xml / com/app/ui/WebViewActivity.java"), web, "file")
    assert not is_match(finding("insecure-webview", "com/app.ui/OtherActivity.java"), web, "file")


def test_method_mode_also_checks_method():
    assert is_match(finding("insecure-webview", "WebViewActivity.java", "onCreate"), WEBVIEW, "method")
    assert not is_match(finding("insecure-webview", "WebViewActivity.java", "onResume"), WEBVIEW, "method")


def test_one_finding_cannot_count_for_two_entries():
    a = Vulnerability(2, "A", ["url-validation"], [Location("Web.java")])
    b = Vulnerability(3, "B", ["url-validation"], [Location("Web.java")])
    assert len(match_findings([finding("url-validation", "Web.java")], [a, b], "file")) == 1


def test_assignment_maximises_matches():
    # B is matched first and grabs finding 0, the only one A accepts. B must move to finding 1 so both count.
    a = Vulnerability(1, "A", ["url-validation"], [Location("Web.java")])
    b = Vulnerability(2, "B", ["url-validation", "insecure-webview"], [Location("Web.java")])
    findings = [finding("url-validation", "Web.java"), finding("insecure-webview", "Web.java")]
    assert match_findings(findings, [b, a], "file") == {1: 0, 2: 1}


def test_finding_is_credited_to_the_entry_it_fits_best():
    # Three entries accept a WebView finding in the same file, but there are only two findings. The settings
    # finding belongs to the entry whose main type it is (17), not to the URL entries that merely also accept it.
    url = Vulnerability(2, "URL validation", ["url-validation", "insecure-webview", "unsafe-intent-handling"], [Location("Web.java")])
    host = Vulnerability(3, "Host check", ["url-validation", "insecure-webview"], [Location("Web.java")])
    settings = Vulnerability(17, "WebView settings", ["insecure-webview"], [Location("Web.java")])
    findings = [finding("insecure-webview", "Web.java"), finding("url-validation", "Web.java")]
    matched = match_findings(findings, [url, host, settings], "file")
    assert len(matched) == 2 and matched[17] == 0 and matched.get(2, matched.get(3)) == 1


def test_best_fit_never_costs_a_match():
    # Fitting best would put the finding with A (main type), but only B can take it: B gets it, A has none to take.
    a = Vulnerability(1, "A", ["insecure-webview"], [Location("Web.java")])
    b = Vulnerability(2, "B", ["url-validation", "insecure-webview"], [Location("Web.java"), Location("Other.java")])
    findings = [finding("insecure-webview", "Web.java"), finding("insecure-webview", "Other.java")]
    assert match_findings(findings, [a, b], "file") == {1: 0, 2: 1}


def test_duplicates_count_once():
    findings = [finding("insecure-webview", "WebViewActivity.java")] * 5
    assert match_findings(findings, [WEBVIEW], "file") == {17: 0}


def test_method_names_as_models_write_them():
    from scanner.scoring.match import _method_name
    assert _method_name("MainActivity.onCreate(Bundle)") == _method_name("onCreate()") == "oncreate"


def test_teacher_findings_become_reference_entries():
    from scanner.scoring.match import teacher_reference
    [ref] = teacher_reference([finding("insecure-webview", "com/app/WebViewActivity.java", "onCreate")])
    assert (ref.id, ref.categories, ref.locations) == (1, ["insecure-webview"], [Location("com/app/WebViewActivity.java", "onCreate")])
    assert is_match(finding("insecure-webview", "WebViewActivity.java"), ref, "file")
    assert not is_match(finding("hardcoded-secret", "WebViewActivity.java"), ref, "file")

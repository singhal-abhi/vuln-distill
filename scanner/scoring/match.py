"""Matching findings to the ground truth. A finding counts only with the right bug type AND the right location."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from scanner.analysis.findings import Finding


@dataclass
class Location:
    file: str
    method: str = ""


@dataclass
class Vulnerability:
    id: int
    name: str
    categories: list[str]       # any of these bug types is accepted
    locations: list[Location]   # any of these places is accepted


def teacher_reference(findings: list[Finding]) -> list[Vulnerability]:
    """The teacher's findings as reference entries, for an app without ground truth. Each entry accepts the finding's
    own bug type at its own file (and method), so scoring a student against them measures agreement with the teacher."""
    return [Vulnerability(id=n, name=f"{f.title or f.type} ({Path(f.file).name})", categories=[f.category],
                          locations=[Location(f.file, f.method)])
            for n, f in enumerate(findings, 1)]


def load_ground_truth(path: Path) -> list[Vulnerability]:
    entries = yaml.safe_load(path.read_text())["vulnerabilities"]
    return [
        Vulnerability(
            id=entry["id"],
            name=entry["name"],
            categories=entry["categories"],
            locations=[Location(**location) for location in entry.get("locations") or []],
        )
        for entry in entries
    ]


def is_match(finding: Finding, vulnerability: Vulnerability, location_mode: str) -> bool:
    if finding.category not in vulnerability.categories:
        return False
    return any(_same_place(finding, location, location_mode) for location in vulnerability.locations)


def _same_place(finding: Finding, location: Location, mode: str) -> bool:
    if not _same_file(finding.file, location.file):
        return False
    if mode == "method" and location.method:
        return _method_name(finding.method) == _method_name(location.method)
    return True


def _method_name(method: str) -> str:
    """ "MainActivity.onCreate(Bundle)" -> "oncreate" """
    return method.split("(")[0].split(".")[-1].strip().lower()


def _same_file(reported: str, expected: str) -> bool:
    """Paths match when one ends with the other, so "WebViewActivity.java" matches "com/x/WebViewActivity.java".
    How the path is written does not matter: package-style folders ("com/x.ui/Main.java") count as folders, and a
    field naming several files ("AndroidManifest.xml / com/x/Main.java") matches each of them."""
    expected_parts = _path_parts(expected)
    for one in MULTIPLE_FILES.split(reported):
        reported_parts = _path_parts(one)
        shorter = min(len(reported_parts), len(expected_parts))
        if shorter > 0 and reported_parts[-shorter:] == expected_parts[-shorter:]:
            return True
    return False


MULTIPLE_FILES = re.compile(r"\s*[,;]\s*|\s+/\s+|\s+and\s+")   # "A.xml / B.java", "A.java, B.java"


def _path_parts(path: str) -> list[str]:
    """ "com/x.ui/Main.java" -> ["com", "x", "ui", "main.java"]: folders split on / or ., the file keeps its extension."""
    base, extension = os.path.splitext(path.strip().lower())
    parts = [part for part in re.split(r"[/.]", base) if part]
    if parts:
        parts[-1] += extension
    return parts


def match_findings(findings: list[Finding], answer_key: list[Vulnerability], location_mode: str) -> dict[int, int]:
    """Pair findings with vulnerabilities, each used at most once. Returns {vulnerability id: index of its finding}.

    1. As many pairs as possible: one finding must not count for two overlapping ground-truth entries.
    2. Among the ways to get that many, credit each finding to the entry it fits best: the one that lists the
       finding's bug type earliest. An "insecure-webview" finding goes to the WebView-settings entry (its main
       type) rather than to a URL-validation entry that merely also accepts it.
    """
    # Cost of a pair: where the finding's bug type sits in the entry's list (0 = the entry's main type).
    cost = {vuln.id: {i: vuln.categories.index(finding.category)
                      for i, finding in enumerate(findings) if is_match(finding, vuln, location_mode)}
            for vuln in answer_key}
    owner: dict[int, int] = {}   # finding index -> vulnerability id
    while chain := _cheapest_new_pair(cost, owner):
        for vuln_id, i in chain:
            owner[i] = vuln_id
    return {vuln_id: i for i, vuln_id in owner.items()}


def _cheapest_new_pair(cost: dict[int, dict[int, int]], owner: dict[int, int]) -> list[tuple[int, int]]:
    """The cheapest way to add one pair: an unmatched entry takes a finding, and if that finding was in use, its entry
    moves on to another one, and so on until an unused finding is reached. Repeating this until no pair can be added
    gives the most pairs at the lowest total cost (the classic "successive shortest paths" method).

    Returns the (vulnerability id, finding index) pairs to set; empty when no pair can be added.
    """
    owned = {vuln_id: i for i, vuln_id in owner.items()}
    entry_cost = {vuln_id: 0 for vuln_id in cost if vuln_id not in owned}   # unmatched entries start the chain
    finding_cost, reached_from = {}, {}
    changed = True
    while changed:   # relax until stable; costs can drop when an entry gives up a finding it held
        changed = False
        for vuln_id, so_far in list(entry_cost.items()):
            for i, pair_cost in cost[vuln_id].items():
                total = so_far + pair_cost
                if owner.get(i) == vuln_id or total >= finding_cost.get(i, float("inf")):
                    continue
                finding_cost[i], reached_from[i], changed = total, vuln_id, True
                if i in owner:   # its current entry gives it up, and no longer pays for holding it
                    holder = owner[i]
                    entry_cost[holder] = min(entry_cost.get(holder, float("inf")), total - cost[holder][i])

    unused = [i for i in finding_cost if i not in owner]
    if not unused:
        return []
    i = min(unused, key=lambda i: (finding_cost[i], i))
    chain = []
    while True:   # walk back from the unused finding to the unmatched entry that started the chain
        vuln_id = reached_from[i]
        chain.append((vuln_id, i))
        if vuln_id not in owned:
            return chain
        i = owned[vuln_id]

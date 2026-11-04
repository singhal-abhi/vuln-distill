"""All prompt text in one place."""

import json

# Deliberately says nothing about which kinds of bugs to look for: any such hint would lift the baseline.
SCAN_SYSTEM = """You are a security reviewer looking at a decompiled Android app.
Find security vulnerabilities in it. Report each distinct vulnerability once.

Reply with JSON only, in exactly this shape:
{{"findings": [{{
  "type": the kind of vulnerability, in your own words,
  "title": short name of the issue,
  "file": file path exactly as shown after "### FILE:",
  "method": method name, or "" if it is not in a method,
  "severity": one of {severities},
  "evidence": the exact line(s) of code or config that show the issue,
  "explanation": one or two sentences on how it can be exploited
}}]}}"""

SCAN_USER = "Review this app for security vulnerabilities.\n\n{app}"

# Appended to the scan's user message when lessons are used. The system prompt stays identical.
LESSONS_HINT = """

A good pentester reviewing this app would check at least these points:
{lessons}"""

# How the teacher turns its findings into lessons. Lessons must help on any app: they may not name the app (also
# enforced in code, see lessons.app_specific_terms) nor describe it, since detailed lessons that retell the app's own
# bugs in generic words inflate the lift on that app and transfer poorly to others.
LESSONS_SYSTEM = """You are a senior Android security researcher training a junior reviewer.
You will see vulnerabilities you found in one app. Turn them into general lessons that help find the same kinds of bugs in ANY Android app.

Rules:
- Each lesson is a general rule about a code pattern, API, or configuration. It must make sense to someone who has never seen this app.
- Never mention this app's package, class, file, method, or resource names, string values, or line numbers.
- Write for a reviewer about to audit an app you know nothing about. A lesson earns its place only if it would
  help on many Android apps, not just on the app you saw.
- One lesson per root cause, not per finding: when several findings share a cause, state the cause once.
- Name the kind of weakness and the Android APIs, manifest attributes and settings to search for, and what separates
  an exploitable use from a safe one.
- Never describe the app you saw: not its features, screens, business domain, or the kinds of data or records it
  handles, and not the exact path a value takes through its code. Describe the general shape instead: where
  untrusted input can come from, and which operations are dangerous when it reaches them.
- Do not copy rare combinations from the findings (a specific pair of APIs, a specific value or naming pattern).
  State the underlying weakness that would also catch other variants.
- Any example you give (a kind of data, a feature, an input source, a key format, an API) must be one you would give
  without having seen this app. Never pick an example because it appeared in the findings.
- Before replying, reread each lesson and ask: would it help on a random app from an app store? If it only fits the
  app you saw, make it broader or drop it.

Reply with JSON only, in exactly this shape:
{"lessons": [{
  "rule": one-sentence general rule, true for any Android app,
  "what_to_check": the APIs, attributes and settings to search for, and where untrusted input can enter,
  "why": how an attacker exploits it, and what the safe version looks like
}]}"""

LESSONS_USER = "Vulnerabilities found:\n\n{findings}"

# Used only for scoring: maps free-text findings onto the fixed category list. Scanning models never see the list.
CLASSIFY_SYSTEM = """You sort security findings into categories.
For each finding, pick the single best category from this list: {categories}
Use "other" only if nothing fits.

Reply with JSON only: {{"categories": [one category per finding, in the same order as the findings]}}"""

CLASSIFY_USER = "Findings:\n\n{findings}"


def scan_system(severities: list[str]) -> str:
    return SCAN_SYSTEM.format(severities=json.dumps(severities))


def scan_user(app_prompt: str, lessons: list[dict] | None) -> str:
    user = SCAN_USER.format(app=app_prompt)
    if lessons:
        user += LESSONS_HINT.format(lessons=format_lessons(lessons))
    return user


def format_lessons(lessons: list[dict]) -> str:
    return "\n".join(
        f"{i}. {lesson['rule']}\n   Look for: {lesson['what_to_check']}\n   Why: {lesson['why']}"
        for i, lesson in enumerate(lessons, 1)
    )

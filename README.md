# Android vulnerability scanner: teacher → student

A frontier model scans a decompiled Android app, turns its findings into general lessons,
and an open model rescans with those lessons. Recall is measured against a known answer key.

## Setup

```bash
brew install jadx
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # add your API keys
```

## Run

```bash
.venv/bin/python -m scanner ingest                        # show what will be scanned
.venv/bin/python -m scanner run                           # all steps, then prints the report
.venv/bin/python -m scanner run --step teacher            # teacher scan + lessons (once; --force to redo)
.venv/bin/python -m scanner run --step student            # students, no lessons
.venv/bin/python -m scanner run --step student-lessons    # students, with the teacher's lessons
.venv/bin/python -m scanner report                        # re-score saved results (no model calls)
```

Add `--app apps/androgoat.yaml` (or `apps/insecurebank.yaml`) to any command to work on another app.

The scan prompt never names bug types. Models describe findings in their own words; a fixed classifier
model (`classifier` in config) then maps each finding onto `categories` for scoring.
With lessons, the prompt is identical except for a hint and the lessons appended after the app.
Lessons must be general: the prompt forbids naming or describing the app, and lessons that mention the app's
package or class names are rejected in code.

Output goes to `work_dir`: findings and their cost per model and run, `lessons.json`, `report.md`, `scores.json`.
Model replies are cached in `cache_dir` (shared by all apps), so re-running only pays for calls that changed.

## New app or new model

- **App:** copy `apps/androgoat.yaml` and point it at the new APK (`apk`, decompiled into `input_dir` on first run)
  or at an existing jadx output folder (`input_dir`). `ground_truth` is optional: without an answer key you get
  the findings and no scores.
- **Model:** write it as `<provider>/<model id>` in `teacher`, `students` or `classifier` in `config.yaml`, e.g.
  `anthropic/claude-opus-5-5` or `groq/openai/gpt-oss-120b` (options are listed there).
  Any OpenAI-compatible server is a new entry under `providers`.

Free tiers limit requests per day (OpenRouter's free models stop at a daily cap without account credit), so a run
with several students and runs can hit the cap; cached calls are kept, and re-running continues from there.

## Layout

| Path | Does |
|---|---|
| `scanner/__main__.py` | Command line: `ingest`, `run`, `report` |
| `scanner/pipeline.py` | The loop: teacher once, then each student without and with lessons |
| `scanner/config.py`, `store.py` | Settings (with the optional app file), saved findings and lessons |
| `scanner/ingest/` | Loads the decompiled app: manifest, the app's own code, key resources, library list |
| `scanner/llm/` | One `complete(system, user)` interface over Anthropic and OpenAI-compatible APIs; retries, the reply cache, tokens and cost |
| `scanner/analysis/` | What models are asked to do: scan the app, classify findings (scoring only), write general lessons; all prompts and JSON schemas |
| `scanner/scoring/` | Finding ↔ answer key (right bug type **and** right location, one-to-one) and the fixed-layout report |
| `apps/`, `ground_truth/` | Per-app settings and answer keys (InsecureShop is the default in `config.yaml`) |

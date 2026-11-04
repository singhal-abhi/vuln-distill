# vuln-distill: Android vulnerability scanning, teacher → student

**Write-up** (results, match function, models, scaling to large apps, dynamic analysis):
[Google Doc](https://docs.google.com/document/d/1Q4feudrnsOFKK3dwODNCXnYwBfsNWFHjv8bceQGSxKk/edit)

A frontier model (the **teacher**) scans a decompiled Android app, then turns what it found into **general lessons**.
An open model (the **student**) scans the same app twice, without and with those lessons.

**Scoring is optional.** It needs an answer key (the app's known vulnerabilities, see [`ground_truth/`](ground_truth/))
and measures one thing: the student's recall without lessons vs with lessons. Everything else in the report (the
teacher's own recall as a reference, the per-vulnerability table, cost) is extra detail. Without an answer key, the
pipeline runs the same and you get the findings and lessons.

## 1. Setup

You need Python 3.10+, [jadx](https://github.com/skylot/jadx) (decompiles the APK) and API keys.

```bash
git clone https://github.com/singhal-abhi/vuln-distill.git
cd vuln-distill

brew install jadx                       # macOS; on Linux, see the jadx releases page. Pulls in Java if needed.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env                    # then fill in the keys you use (see below)
```

Keys in `.env`, matched to the models chosen in `config.yaml`:

| Key | Needed for (default config) |
|---|---|
| `ANTHROPIC_API_KEY` | teacher and classifier (`anthropic/claude-haiku-5-5`) |
| `OPENROUTER_API_KEY` | student (`openrouter/nvidia/nemotron-3.5-super-vl:free`) |
| `OPENAI_API_KEY`, `GROQ_API_KEY` | only if you pick models from those providers |

## 2. Get an app to scan

Put the APK where `config.yaml` (or an app file in `apps/`) expects it. It is decompiled automatically on first run.

```bash
mkdir -p target/androgoat target/insecurebank
curl -L -o target/InsecureShop.apk \
  https://github.com/hax0rgb/InsecureShop/releases/download/v1.0/InsecureShop.apk
curl -L -o target/androgoat/AndroGoat.apk \
  https://github.com/satishpatnayak/AndroGoat/releases/download/v2.0.1/AndroGoat.apk
curl -L -o target/insecurebank/InsecureBankv2.apk \
  https://raw.githubusercontent.com/dineshshetty/Android-InsecureBankv2/master/InsecureBankv2.apk
```

The SHA-256 of each APK is recorded at the top of its answer key in `ground_truth/`.

## 3. Run

```bash
.venv/bin/python -m scanner ingest      # check what will be scanned (files, resources, prompt size); no model calls
.venv/bin/python -m scanner run         # teacher scan + lessons, then student without and with lessons, then the report
```

`run` prints progress and the cost of every scan, then the report. Step by step instead:

```bash
.venv/bin/python -m scanner run --step teacher            # teacher scan + lessons (done once; --force to redo)
.venv/bin/python -m scanner run --step student            # students, no lessons
.venv/bin/python -m scanner run --step student-lessons    # students, with the teacher's lessons
.venv/bin/python -m scanner report                        # re-score saved results (no model calls)
```

Add `--app apps/androgoat.yaml` (or `apps/insecurebank.yaml`) to any command to work on another app. Without
`--app`, the app in `config.yaml` is used (InsecureShop).

Run the tests with `.venv/bin/python -m pytest`.

## 4. Output

Everything goes to the app's `work_dir` (for example `work/insecureshop/`):

| File | Contains |
|---|---|
| `report.md` | Only with an answer key: the student's recall without vs with lessons (the lift); then, for reference, the teacher's recall, cost, a per-vulnerability table and the lessons |
| `scores.json` | The same numbers, machine-readable |
| `lessons.json` | The teacher's lessons, plus any rejected as app-specific (with the reason) |
| `findings/<model>/<condition>/` | Every finding of every run, and what each run cost |

Model replies are cached in `work/cache/` (shared by all apps), so re-running only pays for calls that changed.

## 5. Scan a new app or use another model

- **New app:** copy `apps/androgoat.yaml`, point `apk` at the new APK and give it its own `work_dir`. Leave out
  `ground_truth` unless you have an answer key: without one you get the findings and lessons, and no scores.
- **Another model:** set `teacher`, `students` or `classifier` in `config.yaml` to `<provider>/<model id>`, for
  example `anthropic/claude-sonnet-5-5` or `groq/openai/gpt-oss-120b`. Options are listed there. Any
  OpenAI-compatible server is one more entry under `providers`.

Free tiers limit requests (OpenRouter's free models cap requests per day without account credit; Groq's free tier
caps tokens per minute below the size of one scan). Cached calls are kept, so re-running continues where it stopped.

## How it works

- **Scan:** the prompt holds the manifest, the app's own code, key resources and the library list, and never names
  bug types. Models describe findings in their own words.
- **Classify (scoring only):** a fixed classifier model maps each finding onto `categories` in `config.yaml`, the
  same names the answer keys use. Scanning models never see this list.
- **Lessons:** the teacher writes rules meant for any Android app. The prompt forbids naming or describing the app,
  and lessons that name its package or classes are rejected in code.
- **Score (optional):** a finding counts when its category and its file match an answer-key entry, one finding per
  entry. The number that matters is the student's recall with lessons minus without.

## Layout

| Path | Does |
|---|---|
| [`scanner/`](scanner/) | The package: command line, the loop, settings, saved results |
| [`scanner/ingest/`](scanner/ingest/) | Decompiles and loads the app |
| [`scanner/llm/`](scanner/llm/) | Model providers, retries, the reply cache, tokens and cost |
| [`scanner/analysis/`](scanner/analysis/) | Scanning, classifying, lessons; all prompts |
| [`scanner/scoring/`](scanner/scoring/) | Matching against the answer key, the report |
| [`apps/`](apps/) | Per-app settings for apps other than the default |
| [`ground_truth/`](ground_truth/) | Answer keys |
| [`tests/`](tests/) | Unit tests |

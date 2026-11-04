# analysis

What the models are asked to do. All prompt text lives in `prompts.py`.

| File | Does |
|---|---|
| `scan.py` | Scans the app with one model, optionally with lessons appended, then classifies the findings. Returns findings and the run's cost. |
| `classify.py` | Scoring only: maps each free-text finding onto one of `categories` in config. Scanning models never see that list. |
| `lessons.py` | The teacher turns its findings into general lessons in one call, then any lesson naming the app's package or classes, or a line number, is rejected. |
| `findings.py` | The `Finding` record and tolerant parsing of model replies (fenced or bare JSON, null fields, odd paths). |
| `prompts.py` | Every prompt. The scan prompt names no bug types; the lessons prompt forbids naming or describing the app. |
| `schemas.py` | JSON schemas sent to models that support structured output. |

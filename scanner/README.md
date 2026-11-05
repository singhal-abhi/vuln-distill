# scanner

The Python package. Run it as `python -m scanner {ingest,run,report}` (see the main README).

| File | Does |
|---|---|
| `__main__.py` | Command line: `ingest`, `run`, `report`, with `--step`, `--force`, `--config`, `--app` |
| `pipeline.py` | The loop: the teacher scans once and writes lessons, then each student scans without and with them |
| `config.py` | Loads `config.yaml` and `.env`; `--app` swaps in another app's `app` section |
| `store.py` | Saves and loads findings, their cost, and the lessons, under the app's `work_dir` |

| Folder | Does |
|---|---|
| [`ingest/`](ingest/) | Decompiles and loads the app |
| [`llm/`](llm/) | Talks to models |
| [`analysis/`](analysis/) | What models are asked to do, and all prompts |
| [`scoring/`](scoring/) | Matching against the ground truth, the report |

A teacher's scan is saved and reused (re-run with `--force`); its lessons are redone only when missing or empty.

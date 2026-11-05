# tests

Unit tests, no network or API keys needed:

```bash
.venv/bin/python -m pytest
```

| File | Covers |
|---|---|
| `test_parsing.py` | Parsing model replies, the classifier's labels, the lesson filter, the prompts |
| `test_match.py` | Matching findings to ground-truth entries: files, methods, path notations, one-to-one pairing |
| `test_cache.py` | The reply cache, re-asking on bad replies, cost accounting |
| `test_models.py` | Structured-output detection, model names, JSON schemas |
| `test_pipeline.py` | Lessons gating, merging teacher runs, saving and loading findings |

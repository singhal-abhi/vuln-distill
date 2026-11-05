# Example lessons

The lessons the teacher (`anthropic/claude-haiku-5-5`) wrote in the final setup (the general lessons prompt in
[`scanner/analysis/prompts.py`](../../scanner/analysis/prompts.py)), one file per app. These are the lessons behind the
results in the write-up. A `run` writes the same kind of file to the app's `work_dir` as `lessons.json`.

| File | App | Lessons |
|---|---|---:|
| [`insecureshop.json`](insecureshop.json) | InsecureShop | 19 |
| [`insecurebankv2.json`](insecurebankv2.json) | InsecureBankv2 | 16 |
| [`androgoat.json`](androgoat.json) | AndroGoat | 16 |

Each file holds the teacher, the lessons (`rule`, `what_to_check`, `why`), any lessons rejected as app-specific (none
here) and what writing them cost.

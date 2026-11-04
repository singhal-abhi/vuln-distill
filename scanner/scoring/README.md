# scoring

Turns saved findings into numbers. Makes no model calls.

| File | Does |
|---|---|
| `match.py` | Loads an answer key and pairs findings with its entries. A finding matches when its category is one the entry accepts and its file is one of the entry's locations (optionally the method too: `match.location` in config). Each finding counts for at most one entry; among equally good pairings, a finding goes to the entry whose main bug type it is. |
| `report.py` | Writes `report.md` and `scores.json`: recall per model and run, lift from lessons, cost, a per-vulnerability table, and the lessons. |

# scoring

Optional: runs only when the app has an answer key. Turns saved findings into one number that matters, the
student's recall with lessons minus without, plus reference detail. Makes no model calls.

| File | Does |
|---|---|
| `match.py` | Loads an answer key and pairs findings with its entries. A finding matches when its category is one the entry accepts and its file is one of the entry's locations (optionally the method too: `match.location` in config). Each finding counts for at most one entry; among equally good pairings, a finding goes to the entry whose main bug type it is. |
| `report.py` | Writes `report.md` and `scores.json`: the student's lift from lessons first; then, for reference, the teacher's recall, cost, a per-vulnerability table and the lessons. |

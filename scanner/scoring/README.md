# scoring

Turns saved findings into one number that matters, the student's score with lessons minus without, plus reference
detail. Makes no model calls. The reference is the app's ground truth when it has one (the score is recall), otherwise
the teacher's findings (the score is agreement with the teacher).

| File | Does |
|---|---|
| `match.py` | Loads a ground-truth list (or turns the teacher's findings into reference entries: `teacher_reference`) and pairs findings with its entries. A finding matches when its category is one the entry accepts and its file is one of the entry's locations (optionally the method too: `match.location` in config). Each finding counts for at most one entry; among equally good pairings, a finding goes to the entry whose main bug type it is. |
| `report.py` | Picks the reference, then writes `report.md` and `scores.json`: the student's lift from lessons first; then, for reference, the teacher's row, cost, a per-item table and the lessons. Against the teacher's own findings, the teacher is not scored. |

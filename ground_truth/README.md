# ground_truth

Answer keys: the known vulnerabilities of each test app. They are used only for scoring and never shown to a model.

| File | App | Entries |
|---|---|---|
| `insecureshop.yaml` | InsecureShop | 19 |
| `androgoat.yaml` | AndroGoat | 26 |
| `insecurebank.yaml` | InsecureBankv2 | 18 |

Each entry lists the bug types it accepts (`categories`, from the list in `config.yaml`) and where it is
(`locations`: a file, optionally a method). A finding matches when both agree. The comment at the top of each file
records which APK it was written for (with its hash) and the judgement calls made: entries left out (runtime-only or
server-side issues), merged or added.

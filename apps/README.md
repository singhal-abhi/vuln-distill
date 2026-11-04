# apps

Per-app settings, for scanning an app other than the default one in `config.yaml`. Each file holds only an `app`
section, which replaces the one in `config.yaml`:

```bash
.venv/bin/python -m scanner run --app apps/androgoat.yaml
```

| File | App |
|---|---|
| `androgoat.yaml` | AndroGoat (OWASP), v2.0.1 release APK |
| `insecurebank.yaml` | InsecureBankv2 |

To add an app, copy one of these and change the paths:

```yaml
app:
  input_dir: target/myapp/decompiled   # jadx output; created from `apk` on first run
  apk: target/myapp/MyApp.apk
  work_dir: work/myapp                 # findings, lessons, report
  ground_truth: ground_truth/myapp.yaml   # optional: only to score the student's lift; leave out if you have none
```

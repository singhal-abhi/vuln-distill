# ingest

Turns an APK into what the models read.

`app.py`:
- `decompile`: runs jadx into a temporary folder and renames it when done, so an interrupted run never leaves a
  half-written app behind.
- `load_app`: reads the manifest, the app's own code (its package plus any `ingest.extra_app_packages`), the
  resources listed in `ingest.resource_globs`, and the third-party library list. Build-generated files in
  `ingest.exclude_files` / `exclude_dirs` are skipped.
- `App.to_prompt()`: the app as one text block, each file under a `### FILE: <path>` header that findings refer to.
- `App.identifiers()`: the app's package and class names, used to reject lessons that mention them.

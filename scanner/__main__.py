"""Command line: python -m scanner {ingest,run,report} [--step STEP] [--force] [--config config.yaml] [--app apps/x.yaml]"""

import argparse

from scanner.config import load_config, resolve
from scanner.ingest.app import load_app
from scanner.analysis.scan import scan_prompt
from scanner.llm.context import estimate_tokens
from scanner.pipeline import STEPS, run
from scanner.scoring.report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(prog="scanner")
    parser.add_argument("command", choices=["ingest", "run", "report"],
                        help="ingest: show what gets scanned | run: teacher/student loop | report: re-score saved results")
    parser.add_argument("--step", choices=STEPS, help="run only this step (default: all three, teacher skipped if done)")
    parser.add_argument("--force", action="store_true", help="redo the teacher step even if its results exist")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--app", help="file with just an `app` section, replacing the one in the config (a different app)")
    args = parser.parse_args()
    config = load_config(args.config, args.app)

    if args.command != "run" and (args.step or args.force):
        parser.error("--step and --force only apply to the run command")
    if args.command == "ingest":
        app = load_app(config)
        print(f"Package:   {app.package}")
        print(f"Code:      {len(app.sources)} files")
        print(f"Resources: {', '.join(app.resources) or 'none'}")
        print(f"Libraries: {len(app.libraries)}")
        print(f"Prompt:    up to ~{estimate_tokens(''.join(scan_prompt(app))):,} tokens (upper estimate; checked "
              "against each model's context window before a run)")
        return
    if args.force and args.step not in (None, "teacher"):
        parser.error("--force only applies to the teacher step")
    if args.command == "run":
        run(config, [args.step] if args.step else STEPS, force_teacher=args.force)
    # Scored against the answer key if the app has one, otherwise against the teacher's findings (see report.py).
    report = write_report(config)
    print(report or f"Nothing to score yet: no answer key and no teacher scan. Findings are in "
                    f"{resolve(config, config['app']['work_dir']) / 'findings'}")


if __name__ == "__main__":
    main()

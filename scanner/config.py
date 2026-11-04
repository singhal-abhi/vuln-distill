from pathlib import Path

import yaml
from dotenv import load_dotenv


def load_config(path: str | Path, app: str | Path | None = None) -> dict:
    """Load config.yaml and the .env next to it. Relative paths resolve against the config's folder.
    `app` is an optional file with just an `app` section, which replaces the one in config.yaml."""
    path = Path(path).resolve()
    load_dotenv(path.parent / ".env")
    config = yaml.safe_load(path.read_text())
    if app:
        config["app"] = yaml.safe_load(Path(app).read_text())["app"]
    config["root"] = path.parent
    return config


def resolve(config: dict, relative: str) -> Path:
    return (config["root"] / relative).resolve()

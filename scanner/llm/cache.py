"""Disk cache for model responses, so re-running or re-scoring never pays for the same call twice."""

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from scanner.llm.usage import Usage


class ResponseCache:
    def __init__(self, directory: Path, refresh: bool = False):
        """With refresh=True nothing is read back: every call goes to the model and overwrites what was cached."""
        self.directory = directory
        self.refresh = refresh
        directory.mkdir(parents=True, exist_ok=True)

    def get(self, key: dict) -> tuple[str, Usage] | None:
        """The cached response and what it cost when it was first asked."""
        path = self._path(key)
        if self.refresh or not path.exists():
            return None
        try:
            entry = json.loads(path.read_text())
            return entry["response"], Usage(**entry["usage"])
        except (ValueError, KeyError, TypeError):   # e.g. a file left half-written by an interrupted run: a miss
            return None

    def put(self, key: dict, response: str, usage: Usage) -> None:
        # Only the response is stored: the key holds the whole prompt (the app's source) and is only needed for its hash.
        path = self._path(key)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"model": key["model"], "tag": key["tag"], "response": response,
                                    "usage": asdict(usage)}))
        os.replace(temp, path)   # atomic, so an interrupted run never leaves a broken entry

    def _path(self, key: dict) -> Path:
        return self.directory / f"{hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()}.json"

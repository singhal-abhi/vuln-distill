import io
import json

import pytest

from scanner.llm import context
from scanner.llm.context import check_fits, estimate_tokens, suggest_models

CONFIG = {"run": {"max_tokens": 100}, "providers": {"openrouter": {"models_url": "https://example.test/models?context={tokens}"}}}
MODELS = [   # what OpenRouter's model list returns, trimmed
    {"id": "big/free", "context_length": 1_000_000, "pricing": {"prompt": "0"}, "supported_parameters": ["structured_outputs"]},
    {"id": "big/paid", "context_length": 200_000, "pricing": {"prompt": "0.0000002"}, "supported_parameters": ["response_format"]},
    {"id": "small/free", "context_length": 1_000, "pricing": {"prompt": "0"}, "supported_parameters": ["structured_outputs"]},
    {"id": "big/no-json", "context_length": 1_000_000, "pricing": {"prompt": "0"}, "supported_parameters": ["tools"]},
    {"id": "router", "context_length": 2_000_000, "pricing": {"prompt": "-1"}, "supported_parameters": ["structured_outputs"]},
    {"id": "big/image", "context_length": 1_000_000, "pricing": {"prompt": "0"}, "supported_parameters": ["structured_outputs"],
     "architecture": {"output_modalities": ["image", "text"]}},
]


class Model:
    def __init__(self, name, context_window):
        self.name, self.context_window = name, context_window


@pytest.fixture
def model_list(monkeypatch):
    urls = []

    def urlopen(url, timeout):
        urls.append(url)
        return io.BytesIO(json.dumps({"data": MODELS}).encode())

    monkeypatch.setattr(context.urllib.request, "urlopen", urlopen)
    return urls


def test_suggestions_fit_return_json_and_list_free_models_first(model_list):
    assert suggest_models(CONFIG, 5_000) and model_list == ["https://example.test/models?context=5000"]   # filtered by OpenRouter
    assert suggest_models(CONFIG, 5_000) == [
        "openrouter/big/free  (1,000,000 tokens, free)",
        "openrouter/big/paid  (200,000 tokens, $0.20 per million input tokens)",
    ]


def test_a_prompt_that_fits_or_an_unknown_window_passes():
    check_fits(Model("m", 1_000), "s", "x" * 1_000, CONFIG)      # ~500 tokens + 100 for the reply
    check_fits(Model("m", None), "s", "x" * 10**7, CONFIG)        # the provider doesn't say: no check


def test_a_prompt_too_big_stops_with_its_size_and_models_that_fit(model_list):
    with pytest.raises(SystemExit) as stopped:
        check_fits(Model("openrouter/small/free", 1_000), "", "x" * 10_000, CONFIG)
    message = str(stopped.value)
    assert f"about {estimate_tokens('x' * 10_000):,} tokens" in message and "accepts 1,000" in message
    assert "openrouter/big/free" in message and "small/free  (" not in message


def test_a_student_too_small_stops_the_run_before_the_teacher_scans(tmp_path, monkeypatch):
    from scanner import pipeline

    calls = []

    class FakeModel(Model):
        def complete(self, system, user, schema=None):
            calls.append(self.name)

    class FakeApp:
        def to_prompt(self):
            return "x" * 10_000

    windows = {"t": 1_000_000, "s": 1_000, "c": None}
    monkeypatch.setattr(pipeline, "build_model", lambda config, name: FakeModel(name, windows[name]))
    monkeypatch.setattr(pipeline, "load_app", lambda config: FakeApp())
    monkeypatch.setattr(context, "suggest_models", lambda config, needed: [])
    config = {"root": tmp_path, "app": {"work_dir": "work"}, "cache_dir": "cache", "teacher": "t",
              "students": ["s"], "classifier": "c", "run": {"max_tokens": 100}, "providers": {}}
    with pytest.raises(SystemExit, match="^s: "):
        pipeline.run(config, pipeline.STEPS)
    assert calls == []   # nothing was sent, the teacher included

import pytest

from scanner.llm.ask import ask
from scanner.llm.cache import ResponseCache
from scanner.analysis.findings import parse_findings
from scanner.llm.models import Reply, TruncatedReply
from scanner.llm.usage import Usage, call_usage

CONFIG = {"run": {"parse_retries": 2, "max_retries": 0}}
SCHEMA = {"name": "findings", "schema": {}}
GOOD = '{"findings": []}'


class Fake:
    name = "fake"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def complete(self, system, user, schema=None):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return Reply(reply, Usage(100, 10, 0.5))


def run(model, cache, usage=None):
    return ask(model, "sys", "user", SCHEMA, parse_findings, cache, CONFIG, tag="run-1", usage=usage or Usage())


def test_unparseable_replies_are_not_cached(tmp_path):
    cache = ResponseCache(tmp_path)
    with pytest.raises(RuntimeError):
        run(Fake(["junk"] * 3), cache)
    model = Fake([GOOD])
    assert run(model, cache) == [] and model.calls == 1   # asked again, not replayed
    replay = Fake([])
    assert run(replay, cache) == [] and replay.calls == 0  # the good reply is cached


def test_corrupt_cache_entry_is_a_miss(tmp_path):
    cache = ResponseCache(tmp_path)
    run(Fake([GOOD]), cache)
    [entry] = tmp_path.glob("*.json")
    entry.write_text('{"respo')   # as if a run was killed mid-write
    model = Fake([GOOD])
    assert run(model, cache) == [] and model.calls == 1


def test_truncated_reply_is_not_retried(tmp_path):
    model = Fake([TruncatedReply("fake"), GOOD])
    with pytest.raises(TruncatedReply):
        run(model, ResponseCache(tmp_path))
    assert model.calls == 1


def test_finding_paths_are_stripped():
    [f] = parse_findings('{"findings": [{"file": " A.java ", "method": null}]}')
    assert (f.file, f.method) == ("A.java", "")


def test_cost_counts_reasks_and_cached_answers_keep_their_cost(tmp_path):
    cache, usage = ResponseCache(tmp_path), Usage()
    run(Fake(["junk", GOOD]), cache, usage)
    assert usage == Usage(200, 20, 1.0)            # the unparseable attempt was paid for too
    replay = Usage()
    run(Fake([]), cache, replay)
    assert replay == Usage(200, 20, 1.0)           # served from the cache, reported at what it cost to produce


def test_call_cost_prefers_reported_then_config_price():
    priced = {"input": 2.0, "output": 10.0}
    assert call_usage(priced, 1_000_000, 100_000).cost == 3.0
    assert call_usage(priced, 1_000_000, 100_000, reported_cost=0.0).cost == 0.0   # e.g. a free OpenRouter model
    assert call_usage(None, 10, 10).cost is None
    total = Usage(1, 1, 1.0)
    total.add(Usage(1, 1, None))
    assert total == Usage(2, 2, None)              # one unknown price makes the sum unknown

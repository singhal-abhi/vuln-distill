"""Ask a model for JSON: cached, retried on API errors, re-asked on unparseable output."""

from typing import Callable, TypeVar

from scanner.llm.cache import ResponseCache
from scanner.llm.models import Model, complete_with_retries
from scanner.llm.usage import Usage

T = TypeVar("T")


def ask(model: Model, system: str, user: str, schema: dict, parse: Callable[[str], T],
        cache: ResponseCache, config: dict, tag: str, usage: Usage) -> T:
    """`schema` is enforced when the model supports it. `tag` separates otherwise identical calls (run 1 vs run 2).
    What the answer cost is added to `usage`, including re-asks; a cached answer counts what it cost when first asked.

    Only replies that parse are cached, so a bad reply is re-asked rather than replayed on the next run.
    """
    settings = config["run"]
    key = {"model": model.name, "system": system, "user": user, "schema": schema, "tag": tag}
    cached = cache.get(key)
    if cached is not None:
        text, spent = cached
        try:
            result = parse(text)
        except ValueError:   # cached before a parser change; ask again
            pass
        else:
            usage.add(spent)
            return result
    spent = Usage()
    for attempt in range(1, settings["parse_retries"] + 2):
        reply = complete_with_retries(model, system, user, schema, settings["max_retries"])
        spent.add(reply.usage)
        try:
            result = parse(reply.text)
        except ValueError as error:   # json.JSONDecodeError is a ValueError
            print(f"  {model.name}: unparseable reply ({error}), attempt {attempt}")
            continue
        cache.put(key, reply.text, spent)
        usage.add(spent)
        return result
    raise RuntimeError(f"{model.name} returned no parseable JSON after {settings['parse_retries'] + 1} attempts")

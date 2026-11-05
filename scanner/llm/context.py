"""Check that a prompt fits a model's context window before sending it, and suggest models that would fit.

The whole app goes into one request, so a large app can be too big for a small model. Better to stop before any
call, with the size and a list of models that fit, than to fail halfway with a provider error.
"""

import json
import urllib.request

# Tokens are estimated, not counted: every provider tokenizes differently and most offer no counting endpoint.
# On our test apps, code came to 2.2 characters per token for Claude and 3 to 4.7 for Nemotron, so characters / 2
# is an upper estimate: it can reject a prompt that would just fit, but should not let through one that doesn't.
CHARS_PER_TOKEN = 2
SUGGESTIONS = 5


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def check_fits(model, system: str, user: str, config: dict) -> None:
    """Stops with an explanation and model suggestions if the prompt plus the reply can't fit the model.
    Does nothing when the model's context window is unknown."""
    window = getattr(model, "context_window", None)
    if not window:
        return
    prompt, reply = estimate_tokens(system + user), config["run"]["max_tokens"]
    if prompt + reply <= window:
        return
    lines = [f"{model.name}: this app's scan prompt is about {prompt:,} tokens (an upper estimate), plus "
             f"{reply:,} for the reply, but the model accepts {window:,}. Choose a model with a larger context "
             "window in config.yaml."]
    suggestions = suggest_models(config, prompt + reply)
    if suggestions:
        lines += ["Models that fit, free first:"] + [f"  {line}" for line in suggestions]
    raise SystemExit("\n".join(lines))


def suggest_models(config: dict, needed: int) -> list[str]:
    """Models with room for `needed` tokens and JSON output, from each provider that publishes a model list
    (`models_url` in config.yaml; OpenRouter does). The provider filters by size where the URL has a `{tokens}`
    slot (OpenRouter's `context` filter); the rest is filtered here. Cheapest first (free first), then largest context."""
    found = []
    for provider_name, provider in config["providers"].items():
        if not provider.get("models_url"):
            continue
        url = provider["models_url"].format(tokens=needed)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                models = json.load(response)["data"]
        except Exception as error:
            print(f"  could not read {url} ({error})")
            continue
        for m in models:
            params = set(m.get("supported_parameters") or [])
            price = float((m.get("pricing") or {}).get("prompt") or 0) * 1_000_000
            outputs = (m.get("architecture") or {}).get("output_modalities") or ["text"]
            # The size is checked again in case a provider ignores the filter. A negative price marks a router whose
            # price depends on where it sends the request: skip those.
            if ((m.get("context_length") or 0) >= needed and params & {"structured_outputs", "response_format"}
                    and price >= 0 and outputs == ["text"]):
                found.append((price, -m["context_length"], f"{provider_name}/{m['id']}"))
    found.sort()
    return [f"{name}  ({-negative_context:,} tokens, {'free' if price == 0 else f'${price:.2f} per million input tokens'})"
            for price, negative_context, name in found[:SUGGESTIONS]]

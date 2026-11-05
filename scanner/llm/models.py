"""One small interface over every model provider. Adding a model or provider is a config change.

Structured output: when a model can enforce a JSON schema, the schema is sent and replies always parse.
Otherwise we fall back to plain JSON mode (or nothing) and rely on the parsers and parse retries.
"""

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Protocol

import anthropic
import openai

from scanner.llm.usage import Usage, call_usage


class TruncatedReply(Exception):
    """The reply hit max_tokens. Re-asking the same prompt would be cut off again, so this is not retried."""

    def __init__(self, model: str):
        super().__init__(f"{model}: reply cut off at max_tokens; raise run.max_tokens in config.yaml")


class EmptyReply(Exception):
    """A response with no choices (free tiers sometimes return an error body with HTTP 200). Retried."""


@dataclass
class Reply:
    text: str
    usage: Usage


class Model(Protocol):
    name: str

    def complete(self, system: str, user: str, schema: dict | None = None) -> Reply: ...


class AnthropicModel:
    def __init__(self, name: str, model_id: str, provider: dict, max_tokens: int, price: dict | None):
        self.name, self.model_id, self.max_tokens, self.price = name, model_id, max_tokens, price
        # max_retries=0: complete_with_retries is the only retry layer, so max_retries in config means what it says.
        self.client = anthropic.Anthropic(api_key=os.environ[provider["api_key_env"]], max_retries=0)

    def complete(self, system: str, user: str, schema: dict | None = None) -> Reply:
        # Every current Claude model enforces a JSON schema, so it is always sent.
        extra = {"output_config": {"format": {"type": "json_schema", "schema": schema["schema"]}}} if schema else None
        response = self.client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            extra_body=extra,
        )
        if response.stop_reason == "max_tokens":
            raise TruncatedReply(self.name)
        text = "".join(block.text for block in response.content if block.type == "text")
        return Reply(text, call_usage(self.price, response.usage.input_tokens, response.usage.output_tokens))


class OpenAICompatibleModel:
    """OpenAI itself, OpenRouter, Groq, or any other server that speaks the OpenAI chat API."""

    def __init__(self, name: str, model_id: str, provider: dict, max_tokens: int, price: dict | None):
        self.name, self.model_id, self.max_tokens, self.price = name, model_id, max_tokens, price
        self.max_tokens_param = provider.get("max_tokens_param", "max_tokens")
        self.extra_body = provider.get("extra_body", {})   # provider-specific request fields from config
        self.output = output_mode(supported_parameters(provider.get("endpoints_url"), model_id))
        print(f"  {name}: {self.output} output")
        self.client = openai.OpenAI(api_key=os.environ[provider["api_key_env"]], base_url=provider.get("base_url"),
                                    max_retries=0)

    def complete(self, system: str, user: str, schema: dict | None = None) -> Reply:
        options = {self.max_tokens_param: self.max_tokens}
        if schema and self.output == "schema":
            options["response_format"] = {"type": "json_schema", "json_schema": {**schema, "strict": True}}
        elif schema and self.output == "json":
            options["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body=self.extra_body,
            **options,
        )
        if not response.choices:
            raise EmptyReply(f"{self.name}: no choices in response")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise TruncatedReply(self.name)
        usage = response.usage
        return Reply(choice.message.content or "",
                     call_usage(self.price, getattr(usage, "prompt_tokens", 0) or 0,
                                getattr(usage, "completion_tokens", 0) or 0, getattr(usage, "cost", None)))


def output_mode(supported: set[str] | None) -> str:
    """"schema" (enforced JSON schema), "json" (JSON mode) or "text", from what the provider says the model
    supports. `supported` is None when the provider has no endpoints_url to ask; then assume support (as on OpenAI).
    """
    if supported is None or "structured_outputs" in supported:
        return "schema"
    return "json" if "response_format" in supported else "text"


def supported_parameters(endpoints_url: str | None, model_id: str) -> set[str] | None:
    """Parameters any provider serving this model supports, from OpenRouter's per-model endpoints API.

    Any provider is enough: with require_parameters (set for OpenRouter in config.yaml), OpenRouter routes only to
    providers that support the request.
    None if the provider has no endpoints_url (nothing to ask). Empty if the lookup fails, which safely
    falls back to no schema.

    Not cached, on purpose. We considered downloading OpenRouter's full model list once and caching it,
    but with one student and one teacher a single per-model request is simpler and lighter. Revisit
    if many OpenRouter models are configured at once.
    """
    if not endpoints_url:
        return None
    url = endpoints_url.format(model=model_id)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            endpoints = json.load(response)["data"]["endpoints"]
    except Exception as error:
        print(f"  could not read {url} ({error}); assuming no structured output")
        return set()
    return {param for endpoint in endpoints for param in endpoint.get("supported_parameters") or []}


PROVIDER_TYPES = {"anthropic": AnthropicModel, "openai_compatible": OpenAICompatibleModel}

RETRYABLE = (
    EmptyReply,
    anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError,
    openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError,
)


def build_model(config: dict, name: str) -> Model:
    """`name` is "<provider>/<model id>" as written in config, e.g. "anthropic/claude-sonnet-5-5"."""
    provider_name, _, model_id = name.partition("/")
    if provider_name not in config["providers"] or not model_id:
        raise SystemExit(f"{name!r}: write models as <provider>/<model id>, with a provider from: "
                         + ", ".join(config["providers"]))
    provider = config["providers"][provider_name]
    key = provider["api_key_env"]
    if not os.environ.get(key):   # unset, or left blank after copying .env.example
        raise SystemExit(f"{name}: {key} is not set. Add it to .env (see .env.example), or pick a model from "
                         "another provider in config.yaml.")
    return PROVIDER_TYPES[provider["type"]](name, model_id, provider, config["run"]["max_tokens"],
                                            config.get("prices", {}).get(name))


def complete_with_retries(model: Model, system: str, user: str, schema: dict | None, max_retries: int) -> Reply:
    for attempt in range(max_retries + 1):
        try:
            return model.complete(system, user, schema)
        except RETRYABLE:
            if attempt == max_retries:
                raise
            time.sleep(min(2**attempt * 5, 120))

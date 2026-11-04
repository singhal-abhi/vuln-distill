# llm

Everything about calling models. Nothing here knows about Android or vulnerabilities.

| File | Does |
|---|---|
| `models.py` | One `complete(system, user, schema)` interface. `AnthropicModel` and `OpenAICompatibleModel` (OpenAI, OpenRouter, Groq, any OpenAI-style server). Models are named `<provider>/<model id>` in config. Sends a JSON schema when the model supports structured output (checked through OpenRouter's endpoints API where available). |
| `ask.py` | One request: answered from the cache if possible, retried on rate limits and server errors, asked again when the reply does not parse. |
| `cache.py` | Disk cache of replies, keyed by model, prompts, schema and run tag. Only replies that parse are stored. |
| `usage.py` | Tokens and dollars per call, summed per run. Cost comes from the provider (OpenRouter reports it) or from `prices` in config. |

Adding a provider is a config change: a new entry under `providers` in `config.yaml`.

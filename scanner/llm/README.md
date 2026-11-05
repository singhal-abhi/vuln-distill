# llm

Everything about calling models. Nothing here knows about Android or vulnerabilities.

| File | Does |
|---|---|
| `models.py` | One `complete(system, user, schema)` interface. `AnthropicModel` and `OpenAICompatibleModel` (OpenAI, OpenRouter, Groq, any OpenAI-style server). Models are named `<provider>/<model id>` in config. Sends a JSON schema when the model supports structured output (checked through OpenRouter's endpoints API where available). Each model also reads its context window from the provider (Anthropic's and Groq's model lists, OpenRouter's endpoints). |
| `context.py` | Before any call, checks the scan prompt plus the reply fits each model's context window (tokens estimated at 2 characters each, an upper estimate). If not, stops and lists models that fit, from OpenRouter's model list. |
| `ask.py` | One request: answered from the cache if possible, retried on rate limits and server errors, asked again when the reply does not parse. |
| `cache.py` | Disk cache of replies, keyed by model, prompts, schema and run tag. Only replies that parse are stored. |
| `usage.py` | Tokens and dollars per call, summed per run. Cost comes from the provider (OpenRouter reports it) or from `prices` in config. |

Adding a provider is a config change: a new entry under `providers` in `config.yaml`.

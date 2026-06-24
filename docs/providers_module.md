# `src/anythink/providers/` — LLM Provider Abstraction Layer

This module is the single integration point for every Large Language Model in
Anythink. It defines the shared data models, the abstract contract all providers
must satisfy, a registry that discovers providers at runtime via entry points,
and nine concrete provider implementations covering cloud and local inference.

---

## Folder Structure

```
src/anythink/providers/
├── __init__.py      # Public re-exports for the package
├── base.py          # All shared data models + BaseProvider ABC + _resolve_params
├── registry.py      # ProviderRegistry — lazy-loaded, cached entry-point discovery
├── anthropic.py     # Claude (Opus / Sonnet / Haiku) via anthropic SDK
├── openai.py        # GPT-4o / GPT-3.5 via openai SDK; also base for LM Studio
├── gemini.py        # Gemini 2.0 / 1.5 via google-generativeai SDK
├── groq.py          # Llama / Mixtral / Gemma via groq SDK (cloud inference)
├── mistral.py       # Mistral Large / Small / Codestral via mistralai SDK
├── cohere.py        # Command R / Command via cohere SDK
├── ollama.py        # Any Ollama model via raw httpx (no optional SDK)
└── lm_studio.py     # LM Studio via OpenAI-compatible local API (subclasses OpenAIProvider)
```

---

## File-by-File Reference

---

### `__init__.py`

**Purpose:** The public API surface for `anythink.providers`. Re-exports the
most commonly needed symbols so callers only need one import.

**Re-exported names:**

| Name | Source |
|------|--------|
| `BaseProvider` | `base.py` |
| `ChatMessage` | `base.py` |
| `ContentPart` | `base.py` |
| `ImagePart` | `base.py` |
| `ModelInfo` | `base.py` |
| `ProviderRegistry` | `registry.py` |
| `StreamChunk` | `base.py` |
| `TextPart` | `base.py` |
| `TokenUsage` | `base.py` |

**Usage:**
```python
from anythink.providers import BaseProvider, ChatMessage, ProviderRegistry
```

---

### `base.py`

**Purpose:** The foundational layer. Contains all shared data models that flow
through the entire call stack, the `BaseProvider` ABC that every provider must
implement, and the `_resolve_params` helper for merging calling conventions.

---

#### Data Models

##### `TextPart` (dataclass)

A plain-text content part used inside a multimodal `ChatMessage`.

| Field | Type  | Description           |
|-------|-------|-----------------------|
| `text`| `str` | The raw text content  |

##### `ImagePart` (dataclass)

A base64-ready image content part for multimodal messages.

| Field       | Type    | Description                                              |
|-------------|---------|----------------------------------------------------------|
| `data`      | `bytes` | Raw binary image data (providers base64-encode as needed)|
| `mime_type` | `str`   | MIME type: `"image/png"`, `"image/jpeg"`, `"image/webp"`, `"image/gif"` |

##### `ContentPart` (type alias)

```python
ContentPart = TextPart | ImagePart
```

The union type for a single part of a multimodal message. Used in
`ChatMessage.content` when content is structured rather than plain text.

---

##### `ChatMessage` (dataclass)

A single turn in a conversation.

| Field       | Type                        | Default               | Description |
|-------------|-----------------------------|-----------------------|-------------|
| `role`      | `Literal["user","assistant","system","tool"]` | — | Who sent the message |
| `content`   | `str \| list[ContentPart]`  | —                     | Plain text or structured multimodal content |
| `timestamp` | `datetime`                  | `datetime.utcnow()`   | When the message was created |
| `metadata`  | `dict[str, Any]`            | `{}`                  | Arbitrary key-value data (e.g. tool call metadata) |

**Content forms:**
- `str` — simple text message, most common case.
- `list[ContentPart]` — multimodal message mixing `TextPart` and `ImagePart`
  objects. Providers convert this to their own wire format in `_build_messages`.

---

##### `GenerationParams` (dataclass)

Tunable LLM generation parameters. Providers only forward the fields they
support; unsupported fields are silently ignored.

| Field               | Type            | Default | Supported by                        |
|---------------------|-----------------|---------|-------------------------------------|
| `temperature`       | `float`         | `0.7`   | All providers                       |
| `max_tokens`        | `int \| None`   | `None`  | All providers                       |
| `top_p`             | `float \| None` | `None`  | All providers except Cohere (uses `p`) |
| `frequency_penalty` | `float \| None` | `None`  | OpenAI, Groq, Mistral only          |
| `presence_penalty`  | `float \| None` | `None`  | OpenAI only                         |

---

##### `TokenUsage` (dataclass)

Token consumption for a single LLM response.

| Field                | Type  | Description                        |
|----------------------|-------|------------------------------------|
| `prompt_tokens`      | `int` | Tokens consumed by the input       |
| `completion_tokens`  | `int` | Tokens generated in the response   |
| `total_tokens`       | `int` | Sum of prompt + completion tokens  |

Present in the `usage` field of the **final** `StreamChunk`. `None` on
mid-stream chunks.

---

##### `StreamChunk` (dataclass)

A single streaming token (or group of tokens) yielded by `stream_chat()`.

| Field          | Type              | Description |
|----------------|-------------------|-------------|
| `text`         | `str`             | The token text. Empty string `""` on the final sentinel chunk. |
| `finish_reason`| `str \| None`     | `"stop"`, `"length"`, `"tool_calls"`, or `None` mid-stream. Set on the final chunk. |
| `usage`        | `TokenUsage \| None` | Token counts. Present only in the final chunk for most providers. |
| `thinking_text`| `str \| None`     | Anthropic extended thinking output when available; `None` otherwise. |

**Streaming protocol:** `stream_chat()` yields `N` mid-stream chunks where
`finish_reason=None`, then one final chunk where `finish_reason` is set (and
`usage` is populated if the provider reports it). Callers accumulate `.text`
from all chunks to build the full response.

---

##### `ModelInfo` (dataclass)

Metadata about a single model available from a provider.

| Field                      | Type   | Default | Description |
|----------------------------|--------|---------|-------------|
| `id`                       | `str`  | —       | Model identifier sent in API calls (e.g. `"gpt-4o"`) |
| `display_name`             | `str`  | —       | Human-readable label shown in the UI |
| `context_window`           | `int`  | —       | Maximum context size in tokens |
| `supports_vision`          | `bool` | `False` | Whether the model accepts image inputs |
| `supports_function_calling`| `bool` | `False` | Whether the model supports tool/function calls |

---

#### `BaseProvider` (ABC)

All LLM providers inherit from this class. Providers are **pure** — they never
fetch API keys themselves; the caller passes credentials at construction.

**Constructor**

```python
def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None
```

Stores credentials as `self._api_key` and `self._base_url`. Local providers
(Ollama, LM Studio) override `__init__` to set a default base URL.

**Class-level attributes** (set on each concrete subclass)

| Attribute      | Type  | Example        |
|----------------|-------|----------------|
| `name`         | `str` | `"groq"`       |
| `display_name` | `str` | `"Groq"`       |

**Abstract methods**

```python
def stream_chat(
    self,
    messages: list[ChatMessage],
    model: str,
    *,
    max_tokens: int | None = None,
    temperature: float = 0.7,
    gen_params: GenerationParams | None = None,
) -> AsyncIterator[StreamChunk]
```
Async generator. Streams completion tokens as `StreamChunk` objects. When
`gen_params` is provided its fields take precedence over the flat `temperature`
/ `max_tokens` kwargs, preserving backward compatibility. The last yielded
chunk has `finish_reason` set.

```python
async def list_models(self) -> list[ModelInfo]
```
Returns all available models. Most providers fall back to a hardcoded
`_KNOWN_MODELS` list if the API call fails.

```python
async def test_connection(self) -> bool
```
Returns `True` if the provider is reachable with the current credentials.
Used by `anythink keys test` and `anythink doctor`.

```python
@property
def supports_vision(self) -> bool
```
`True` if the provider accepts image inputs in at least some models.

```python
@property
def requires_api_key(self) -> bool
```
`False` for local providers (Ollama, LM Studio). Used by key-management UI to
skip key prompts for local backends.

**Concrete helper method**

```python
def _content_to_text(self, content: str | list[ContentPart]) -> str
```
Extracts plain text from `content`, joining all `TextPart` objects with a
space and silently dropping any `ImagePart` objects. Used by providers that
do not support multimodal input (Groq, Mistral, Cohere, Ollama).

---

#### `_resolve_params` (module-level function)

```python
def _resolve_params(
    gen_params: GenerationParams | None,
    temperature: float,
    max_tokens: int | None,
) -> GenerationParams
```

Merges the two calling conventions into one `GenerationParams` object:
- If `gen_params` is not `None`, returns it directly (V3 path — caller sets all params).
- Otherwise wraps the flat `temperature` / `max_tokens` kwargs into a new
  `GenerationParams` (legacy path — older callers).

Every `stream_chat()` implementation must call this at the top before building
the API payload:

```python
params = _resolve_params(gen_params, temperature, max_tokens)
```

---

### `registry.py`

**Purpose:** Discovers and caches provider classes via the
`anythink.providers` entry-point group. Used by the app orchestrator to
instantiate any provider by name.

#### `ProviderRegistry`

**Constructor:** `ProviderRegistry()` — no arguments. Initialises
`self._cache = None`.

**Lazy loading:** The first call to any method that needs provider classes
triggers `_load()`, which reads all registered entry points and caches the
result as `dict[str, type[BaseProvider]]`. Subsequent calls skip discovery.

**Methods**

| Method | Signature | Description |
|--------|-----------|-------------|
| `_load` | `() -> dict[str, type[BaseProvider]]` | Internal. Reads entry points, populates and returns `_cache`. Raises `PluginError` if any entry point fails to import. |
| `get` | `(name: str) -> type[BaseProvider]` | Returns the provider **class** (not an instance). Raises `PluginError` with the list of available providers if `name` is unknown. |
| `list_names` | `() -> list[str]` | Returns sorted list of all registered provider names. |
| `instantiate` | `(name, api_key, base_url) -> BaseProvider` | Calls `get()` then constructs the class with the given credentials. The primary way to create a provider at runtime. |
| `invalidate_cache` | `() -> None` | Clears `_cache`. Called after `anythink plugins install` / `remove` so new entry points are discovered on the next use. |

**Error behaviour:**
- Failed entry point load → `PluginError` (propagated immediately, not swallowed).
  This is intentional: a broken provider plugin should surface loudly.
- Unknown provider name → `PluginError` with a list of available names.

**Entry-point group constant:**
```python
_ENTRY_POINT_GROUP = "anythink.providers"
```

**Registration in `pyproject.toml`:**
```toml
[project.entry-points."anythink.providers"]
anthropic = "anythink.providers.anthropic:AnthropicProvider"
openai    = "anythink.providers.openai:OpenAIProvider"
gemini    = "anythink.providers.gemini:GeminiProvider"
groq      = "anythink.providers.groq:GroqProvider"
mistral   = "anythink.providers.mistral:MistralProvider"
cohere    = "anythink.providers.cohere:CohereProvider"
ollama    = "anythink.providers.ollama:OllamaProvider"
lm_studio = "anythink.providers.lm_studio:LMStudioProvider"
```

---

### `anthropic.py`

**Purpose:** Implements the Claude family of models via the `anthropic` Python
SDK (`pip install anythink[anthropic]`).

#### `AnthropicProvider`

```
name         = "anthropic"
display_name = "Anthropic"
requires_api_key  = True
supports_vision   = True
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context | Vision | Function Calling |
|----------|-------------|---------|--------|-----------------|
| `claude-opus-4-8` | Claude Opus 4.8 | 200K | Yes | Yes |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 200K | Yes | Yes |
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | 200K | Yes | Yes |

**`_client() -> anthropic.AsyncAnthropic`**

Lazy-imports the `anthropic` SDK; raises `ProviderUnavailableError` on
`ImportError`. Returns `AsyncAnthropic(api_key=self._api_key)`.

**`_build_messages(messages) -> tuple[list[dict], str | None]`**

Converts `ChatMessage` list to the Anthropic wire format. Critically,
**extracts system messages** into a separate `system` string (Anthropic's API
takes `system` as a top-level parameter, not as a message role).

- `TextPart` → `{"type": "text", "text": ...}`
- `ImagePart` → `{"type": "image", "source": {"type": "base64", "media_type": ..., "data": <b64>}}`

Returns `(messages_list, system_prompt_or_None)`.

**`stream_chat()` specifics**

- Calls `_resolve_params` to merge generation params.
- Forwards: `temperature`, `max_tokens` (defaults to 4096 if `None`), `top_p`.
- Does **not** forward `frequency_penalty` or `presence_penalty` (not supported by Anthropic).
- Uses `client.messages.stream()` async context manager; iterates `.text_stream`
  for mid-stream text, then calls `stream.get_final_message()` for usage stats.
- Final chunk: `StreamChunk(text="", finish_reason=final.stop_reason, usage=...)`.

**`list_models()`** — Returns the static `_KNOWN_MODELS` list (no live API call).

**`test_connection()`** — Makes a minimal `messages.create` call with
`claude-haiku-4-5-20251001`, `max_tokens=1`, and `"hi"`.

**Error mapping**

| SDK exception | Anythink exception |
|---|---|
| `anthropic.AuthenticationError` | `AuthenticationError` |
| `anthropic.RateLimitError` | `RateLimitError` |
| `anthropic.NotFoundError` | `ModelNotFoundError` |
| `anthropic.APIConnectionError` / `httpx.ConnectError` | `ProviderUnavailableError` |

---

### `openai.py`

**Purpose:** GPT-4o and GPT-3.5 via the `openai` Python SDK
(`pip install anythink[openai]`). Also serves as the **base class** for
`LMStudioProvider` since LM Studio exposes an OpenAI-compatible API.

#### `OpenAIProvider`

```
name         = "openai"
display_name = "OpenAI"
requires_api_key  = True
supports_vision   = True
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context | Vision | Function Calling |
|----------|-------------|---------|--------|-----------------|
| `gpt-4o` | GPT-4o | 128K | Yes | Yes |
| `gpt-4o-mini` | GPT-4o Mini | 128K | Yes | Yes |
| `gpt-4-turbo` | GPT-4 Turbo | 128K | Yes | Yes |
| `gpt-3.5-turbo` | GPT-3.5 Turbo | 16,385 | No | Yes |

**`_client() -> openai.AsyncOpenAI`**

Lazy-imports `openai`. If `self._base_url` is set, passes it to `AsyncOpenAI`
(used by `LMStudioProvider`). Uses `api_key or "not-needed"` so local
subclasses can skip key validation.

**`_build_messages(messages) -> list[dict]`**

Converts `ChatMessage` list to OpenAI wire format. Passes system messages
through as-is (OpenAI accepts `"role": "system"` inline):
- `TextPart` → `{"type": "text", "text": ...}`
- `ImagePart` → `{"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}}`

**`stream_chat()` specifics**

- Forwards: `temperature`, `max_tokens`, `top_p`, `frequency_penalty`,
  `presence_penalty` (all four extra params — OpenAI supports them all).
- Uses `client.chat.completions.create(stream=True)`.
- Extracts `chunk.choices[0].delta.content` each iteration; reads usage from
  `chunk.usage` when present (not every provider returns it mid-stream).

**`list_models()`** — Calls `client.models.list()` live and filters to
`gpt-*` models. Falls back to `_KNOWN_MODELS` on any error.

**Error mapping**

| SDK exception | Anythink exception |
|---|---|
| `openai.AuthenticationError` | `AuthenticationError` |
| `openai.RateLimitError` | `RateLimitError` |
| `openai.NotFoundError` | `ModelNotFoundError` |
| `openai.APIConnectionError` / `httpx.ConnectError` | `ProviderUnavailableError` |
| `openai.APIError` (generic) | `ProviderUnavailableError` |

---

### `gemini.py`

**Purpose:** Google Gemini models via the `google-generativeai` SDK
(`pip install anythink[gemini]`).

#### `GeminiProvider`

```
name         = "gemini"
display_name = "Google Gemini"
requires_api_key  = True
supports_vision   = True
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context | Vision | Function Calling |
|----------|-------------|---------|--------|-----------------|
| `gemini-2.0-flash` | Gemini 2.0 Flash | 1M | Yes | Yes |
| `gemini-1.5-pro` | Gemini 1.5 Pro | 2M | Yes | Yes |
| `gemini-1.5-flash` | Gemini 1.5 Flash | 1M | Yes | Yes |

**`_configure()`** — Calls `genai.configure(api_key=self._api_key)` to set the
global API key for the SDK. Raises `ProviderUnavailableError` if the package is
missing.

**`_build_contents(messages) -> list[dict]`**

Converts `ChatMessage` list to Gemini's `contents` format:
- **Skips system messages** (handled separately via `system_instruction`).
- Maps `"user"` → `"user"` and all others → `"model"`.
- `TextPart` → `{"text": ...}`
- `ImagePart` → `{"inline_data": {"mime_type": ..., "data": <raw bytes>}}`
  (Gemini SDK handles base64 encoding internally).

**`_get_system_instruction(messages) -> str | None`**

Scans for the first `"system"` role message and returns its plain text. Used to
pass `system_instruction` when constructing `GenerativeModel`.

**`stream_chat()` specifics**

- Constructs `GenerativeModel(model, system_instruction=system)` with the
  extracted system prompt.
- Forwards: `temperature`, `max_tokens` (as `max_output_tokens`), `top_p`.
- Does **not** forward `frequency_penalty` or `presence_penalty`.
- Calls `genai_model.generate_content_async(..., stream=True)`.
- Reads `response.usage_metadata` after iteration for token counts.

**`list_models()`** — Calls `genai.list_models_async()` live, filters to
models that support `"generateContent"`, strips the `"models/"` prefix from
IDs. Falls back to `_KNOWN_MODELS`.

**Error mapping**

Gemini SDK does not have typed exception subclasses, so errors are classified
by string matching on `str(e).lower()`:

| String match | Anythink exception |
|---|---|
| `"api key"` / `"unauthenticated"` | `AuthenticationError` |
| `"quota"` / `"rate"` | `RateLimitError` |
| `"not found"` / `"does not exist"` | `ModelNotFoundError` |
| anything else | `ProviderUnavailableError` |

---

### `groq.py`

**Purpose:** Cloud-accelerated inference for Llama, Mixtral, and Gemma models
via the `groq` Python SDK (`pip install anythink[groq]`).

#### `GroqProvider`

```
name         = "groq"
display_name = "Groq"
requires_api_key  = True
supports_vision   = False
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context |
|----------|-------------|---------|
| `llama3-8b-8192` | Llama 3 8B | 8,192 |
| `llama3-70b-8192` | Llama 3 70B | 8,192 |
| `llama-3.1-8b-instant` | Llama 3.1 8B Instant | 131,072 |
| `llama-3.1-70b-versatile` | Llama 3.1 70B Versatile | 131,072 |
| `mixtral-8x7b-32768` | Mixtral 8x7B | 32,768 |
| `gemma2-9b-it` | Gemma 2 9B IT | 8,192 |

**`_build_messages(messages)`**

Groq does not support multimodal input. Falls back to `_content_to_text()`
for any `list[ContentPart]` content.

**`stream_chat()` specifics**

- Forwards: `temperature`, `max_tokens`, `top_p`, `frequency_penalty`.
- Does **not** forward `presence_penalty` (not supported by Groq).
- Uses `client.chat.completions.create(stream=True)`.

**Special error handling — context length (HTTP 413)**

Groq enforces strict context limits per model. A 413 response raises a
user-friendly `ProviderError` with the message
`"Message history is too large for this model. Use /clear to reset the conversation."`
This is caught both as `groq.APIStatusError` (status 413) and as
`groq.APIError` (string match on `"too large"` / `"413"` / `"request entity"`).

**Error mapping**

| SDK exception | Anythink exception |
|---|---|
| `groq.AuthenticationError` | `AuthenticationError` |
| `groq.RateLimitError` | `RateLimitError` |
| `groq.NotFoundError` | `ModelNotFoundError` |
| `groq.APIStatusError` (413) / `groq.APIError` ("too large") | `ProviderError` (context limit) |
| `groq.APIConnectionError` / `httpx.ConnectError` | `ProviderUnavailableError` |

---

### `mistral.py`

**Purpose:** Mistral Large, Mistral Small, Mixtral 8x22B, and Codestral via
the `mistralai` Python SDK (`pip install anythink[mistral]`).

#### `MistralProvider`

```
name         = "mistral"
display_name = "Mistral"
requires_api_key  = True
supports_vision   = False
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context | Function Calling |
|----------|-------------|---------|-----------------|
| `mistral-large-latest` | Mistral Large | 128K | Yes |
| `mistral-small-latest` | Mistral Small | 128K | Yes |
| `open-mixtral-8x22b` | Mixtral 8x22B | 65,536 | Yes |
| `codestral-latest` | Codestral | 32,000 | No |

**`_build_messages(messages)`**

Text-only; uses `_content_to_text()` for multimodal content. All roles
passed through as-is.

**`stream_chat()` specifics**

- Forwards: `temperature`, `max_tokens`, `top_p`.
- Does **not** forward `frequency_penalty` or `presence_penalty`.
- Uses `client.chat.stream_async(**kwargs)` — note the Mistral SDK wraps each
  chunk as an `event`; text is at `event.data.choices[0].delta.content`.
- `finish_reason` is coerced to `str` since the Mistral SDK may return an
  enum value.

**Error mapping**

Mistral SDK exceptions classified by string match on HTTP status codes:

| String match | Anythink exception |
|---|---|
| `"401"` / `"unauthorized"` / `"api key"` | `AuthenticationError` |
| `"429"` / `"rate limit"` | `RateLimitError` |
| `"404"` / `"not found"` | `ModelNotFoundError` |
| anything else | `ProviderUnavailableError` |

---

### `cohere.py`

**Purpose:** Cohere Command R family via the `cohere` Python SDK
(`pip install anythink[cohere]`).

#### `CohereProvider`

```
name         = "cohere"
display_name = "Cohere"
requires_api_key  = True
supports_vision   = False
```

**Known models (`_KNOWN_MODELS`)**

| Model ID | Display Name | Context | Function Calling |
|----------|-------------|---------|-----------------|
| `command-r-plus` | Command R+ | 128K | Yes |
| `command-r` | Command R | 128K | Yes |
| `command` | Command | 4,096 | No |
| `command-light` | Command Light | 4,096 | No |

**`_build_chat_history(messages) -> tuple[str, list[dict]]`**

Cohere's API has a unique format: instead of a flat `messages` array, it takes
a `message` string (the latest user turn) plus a `chat_history` array of prior
turns. This method:

1. Maps roles: `"user"` → `"USER"`, `"assistant"` → `"CHATBOT"`, `"system"` → `"SYSTEM"`.
2. The **last** message if its role is `"user"` becomes the `message` parameter.
3. All prior messages become `chat_history` entries with `{"role": ..., "message": ...}`.

**`stream_chat()` specifics**

- Forwards: `temperature`, `max_tokens`, `top_p` (as Cohere's `p` parameter).
- Does **not** forward `frequency_penalty` or `presence_penalty`.
- Uses `client.chat_stream(...)` (synchronous streaming via the async client).
- Iterates events by `event_type`:
  - `"text-generation"` → yields `StreamChunk(text=event.text, finish_reason=None)`.
  - `"stream-end"` → reads `event.response.meta.tokens` for usage, yields final
    `StreamChunk(text="", finish_reason="stop", usage=...)`.

**Error mapping**

| String match | Anythink exception |
|---|---|
| `"unauthorized"` / `"api key"` | `AuthenticationError` |
| `"rate limit"` / `"429"` | `RateLimitError` |
| `"not found"` / `"404"` | `ModelNotFoundError` |
| anything else | `ProviderUnavailableError` |

---

### `ollama.py`

**Purpose:** Any model served by a local Ollama instance. Uses **raw `httpx`**
with no optional SDK — Ollama is always available as long as `httpx` is
installed (a core Anythink dependency).

#### `OllamaProvider`

```
name         = "ollama"
display_name = "Ollama"
requires_api_key  = False
supports_vision   = False
```

**Module-level constant**

```python
_DEFAULT_BASE_URL = "http://localhost:11434"
```

**Constructor**

```python
def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None
```

Overrides the base constructor to store a cleaned base URL:
`self._url = (base_url or _DEFAULT_BASE_URL).rstrip("/")`.
This allows pointing at a remote Ollama instance via `base_url`.

**`_build_messages(messages)`**

Text-only; uses `_content_to_text()` for multimodal content. Roles passed
through as-is.

**`stream_chat()` specifics**

- Forwards: `temperature`, `max_tokens` (as Ollama's `num_predict`), `top_p`.
- Does **not** forward `frequency_penalty` or `presence_penalty`.
- Sends a `POST` to `{self._url}/api/chat` with `stream: true` via
  `httpx.AsyncClient(timeout=120.0)`.
- Uses `client.stream()` to open an HTTP streaming response.
- Parses each NDJSON line via `json.loads(line)`.
  - `data["message"]["content"]` → token text.
  - `data["done"] == True` → sets `finish_reason="stop"` and reads
    `prompt_eval_count` / `eval_count` for `TokenUsage`.
- HTTP 404 → `ModelNotFoundError` with a `ollama pull <model>` hint.

**`list_models()`** — `GET {self._url}/api/tags`, parses the `"models"` array.

**`test_connection()`** — `GET {self._url}/api/tags` with 5-second timeout.

**Error mapping**

| Exception | Anythink exception |
|---|---|
| `httpx.ConnectError` | `ProviderUnavailableError` (with "Is Ollama running?" hint) |
| `httpx.HTTPStatusError` | `ProviderUnavailableError` with status code |
| HTTP 404 on stream | `ModelNotFoundError` with `ollama pull` hint |

---

### `lm_studio.py`

**Purpose:** LM Studio local inference server via its OpenAI-compatible REST
API. Subclasses `OpenAIProvider` — reuses all message building, streaming, and
error handling with only three overrides.

#### `LMStudioProvider(OpenAIProvider)`

```
name         = "lm_studio"
display_name = "LM Studio"
requires_api_key  = False
supports_vision   = True   (depends on loaded model, but many support it)
```

**Module-level constant**

```python
_DEFAULT_BASE_URL = "http://localhost:1234/v1"
```

**Constructor**

```python
def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
    super().__init__(api_key="lm-studio", base_url=base_url or _DEFAULT_BASE_URL)
```

Always passes `api_key="lm-studio"` to `OpenAIProvider._client()` so the
`openai` SDK does not complain about a missing key, while still routing all
requests to the local LM Studio endpoint.

**Overridden properties**

| Property | Value | Reason |
|----------|-------|--------|
| `requires_api_key` | `False` | No cloud key needed |
| `supports_vision` | `True` | Many LM Studio models support vision |

**Everything else** — `stream_chat()`, `list_models()`, `test_connection()`,
and `_build_messages()` are all inherited from `OpenAIProvider` unchanged.

---

## Generation Parameter Support Matrix

| Parameter | Anthropic | OpenAI | Gemini | Groq | Mistral | Cohere | Ollama | LM Studio |
|-----------|:---------:|:------:|:------:|:----:|:-------:|:------:|:------:|:---------:|
| `temperature` | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `max_tokens` | Yes | Yes | Yes (as `max_output_tokens`) | Yes | Yes | Yes | Yes (as `num_predict`) | Yes |
| `top_p` | Yes | Yes | Yes | Yes | Yes | Yes (as `p`) | Yes | Yes |
| `frequency_penalty` | No | Yes | No | Yes | No | No | No | Yes |
| `presence_penalty` | No | Yes | No | No | No | No | No | Yes |

---

## Message Format Transformation Summary

Each provider transforms `list[ChatMessage]` into its own wire format:

| Provider | System message handling | Multimodal support | Format notes |
|----------|------------------------|--------------------|--------------|
| Anthropic | Extracted into top-level `system` param | Yes (base64 inline) | `TextPart`→text block, `ImagePart`→base64 source |
| OpenAI | Inline as `{"role": "system", ...}` | Yes (data URL) | `ImagePart`→`data:<mime>;base64,<b64>` URL |
| Gemini | Via `system_instruction` on `GenerativeModel` | Yes (raw bytes) | SDK handles base64; images as `inline_data` |
| Groq | Inline (text only) | No (drops images) | Uses `_content_to_text()` |
| Mistral | Inline (text only) | No (drops images) | Uses `_content_to_text()` |
| Cohere | As `"SYSTEM"` role in `chat_history` | No (drops images) | Last user turn separated as `message` param |
| Ollama | Inline (text only) | No (drops images) | Uses `_content_to_text()` |
| LM Studio | Same as OpenAI (inherited) | Yes (inherited) | Same as OpenAI |

---

## How to Add a New Provider

1. Create `src/anythink/providers/<name>.py` subclassing `BaseProvider`.
2. Set `name` and `display_name` class attributes.
3. Define `_KNOWN_MODELS: list[ModelInfo]` as a fallback.
4. Implement a `_client()` method that lazy-imports the SDK and raises
   `ProviderUnavailableError` on `ImportError`.
5. Implement `_build_messages()` to convert `list[ChatMessage]` to the SDK
   format.
6. Implement `stream_chat()`: call `_resolve_params()` first, build kwargs
   selectively (only forward params the SDK supports), iterate the stream,
   yield `StreamChunk` objects, and map SDK exceptions to Anythink exceptions.
7. Implement `list_models()` with a live API call that falls back to
   `_KNOWN_MODELS`.
8. Implement `test_connection()` — typically just calls `list_models()`.
9. Declare `supports_vision` and `requires_api_key` properties.
10. Register in `pyproject.toml`:

    ```toml
    [project.entry-points."anythink.providers"]
    myprovider = "anythink.providers.myprovider:MyProvider"
    ```

11. Add the SDK to the matching optional extra in `pyproject.toml`.

---

## Error Hierarchy

All provider errors are subclasses of `ProviderError` (which is itself a
subclass of `AnythinkError`). Every exception carries a `provider` field with
the provider name for logging, and a `user_message` for terminal display.

```
ProviderError(provider="anthropic")
  ├── AuthenticationError    — wrong or missing API key
  ├── RateLimitError         — too many requests / quota exceeded
  ├── ModelNotFoundError     — requested model does not exist
  └── ProviderUnavailableError — network failure, SDK missing, or server down
```

Note: `ProviderError` itself (the base, not the leaf) is raised by Groq for
the context-length-exceeded case — this is intentional since the condition
is user-fixable but doesn't fit the other leaf categories cleanly.

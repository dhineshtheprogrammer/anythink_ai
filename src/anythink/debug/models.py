"""Data models for the V3.2.0 debug infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anythink.providers.base import GenerationParams, TokenUsage
    from anythink.rag.models import RetrievalResult


@dataclass
class TokenEntry:
    """A single token captured during a token-trace (Level 3)."""

    index: int
    text: str
    delta_ms: float  # milliseconds since the previous token


@dataclass
class ToolCallEntry:
    """Record of a single tool call that occurred during a request."""

    name: str
    arguments: dict[str, Any]
    result_summary: str
    duration_s: float
    success: bool
    used_in_response: bool = False  # heuristic: result text appears in response buffer


@dataclass
class PluginEvent:
    """A single plugin hook invocation captured during a request."""

    plugin_name: str
    hook_name: str
    duration_ms: float
    modified: bool  # True if the hook returned a non-passthrough value


@dataclass
class HttpLogEntry:
    """One HTTP request/response pair captured by the API logger."""

    method: str
    url: str
    status_code: int
    request_headers: dict[str, str]
    request_body_snippet: str  # first 2000 chars of the JSON body
    response_headers: dict[str, str]
    round_trip_ms: float


@dataclass
class RequestDebugRecord:
    """All captured debug data for a single AI request/response cycle.

    Created by DebugManager.begin_request() and mutated progressively
    throughout _stream_response() before being finalised with
    DebugManager.finalize_request().
    """

    request_id: int
    session_id: str
    timestamp: datetime
    model_id: str
    provider_name: str
    alias_name: str
    prompt_payload: list[dict[str, Any]]  # serialised ChatMessages as-sent
    gen_params: GenerationParams | None

    # ── timing (monotonic seconds from time.monotonic()) ──────────────────
    t_start: float = 0.0
    t_prompt_assembled: float = 0.0
    t_rag_start: float | None = None
    t_rag_end: float | None = None
    t_search_start: float | None = None
    t_search_end: float | None = None
    t_api_sent: float = 0.0
    t_first_token: float | None = None
    t_stream_end: float = 0.0
    t_render_end: float = 0.0

    # ── outcomes ──────────────────────────────────────────────────────────
    stop_reason: str | None = None
    usage: TokenUsage | None = None
    completion_tokens: int = 0
    tokens_per_second: float | None = None
    was_stopped_by_user: bool = False

    # ── RAG data ──────────────────────────────────────────────────────────
    rag_query: str = ""
    rag_results: list[RetrievalResult] = field(default_factory=list)
    rag_embedding_ms: float | None = None
    rag_candidates_evaluated: int = 0

    # ── detail layers ─────────────────────────────────────────────────────
    tool_calls: list[ToolCallEntry] = field(default_factory=list)
    plugin_events: list[PluginEvent] = field(default_factory=list)
    http_log: HttpLogEntry | None = None
    token_trace: list[TokenEntry] = field(default_factory=list)  # Level 3 only
    agent_thinking: str = ""  # Anthropic extended thinking, if available

    # ── convenience properties ────────────────────────────────────────────

    def ttft_ms(self) -> float | None:
        """Time-to-first-token in milliseconds, or None if not yet captured."""
        if self.t_first_token is None or self.t_api_sent == 0.0:
            return None
        return (self.t_first_token - self.t_api_sent) * 1000

    def stream_duration_ms(self) -> float:
        """Duration of the token stream from first to last token in ms."""
        if self.t_first_token is None or self.t_stream_end == 0.0:
            return 0.0
        return (self.t_stream_end - self.t_first_token) * 1000

    def total_wall_ms(self) -> float:
        """Total wall-clock time from request start to render complete in ms."""
        if self.t_start == 0.0 or self.t_render_end == 0.0:
            return 0.0
        return (self.t_render_end - self.t_start) * 1000

    def rag_duration_ms(self) -> float | None:
        """RAG retrieval duration in ms, or None if RAG was not active."""
        if self.t_rag_start is None or self.t_rag_end is None:
            return None
        return (self.t_rag_end - self.t_rag_start) * 1000

    def search_duration_ms(self) -> float | None:
        """Web search duration in ms, or None if search was not active."""
        if self.t_search_start is None or self.t_search_end is None:
            return None
        return (self.t_search_end - self.t_search_start) * 1000

    def prompt_assembly_ms(self) -> float:
        """Time spent assembling the prompt payload in ms."""
        if self.t_start == 0.0 or self.t_prompt_assembled == 0.0:
            return 0.0
        return (self.t_prompt_assembled - self.t_start) * 1000

    def api_overhead_ms(self) -> float:
        """Time from prompt-assembled to first-token (API call overhead) in ms."""
        if self.t_prompt_assembled == 0.0 or self.t_first_token is None:
            return 0.0
        return (self.t_first_token - self.t_prompt_assembled) * 1000

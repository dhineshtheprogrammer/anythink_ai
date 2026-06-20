"""Anythink exception hierarchy."""


class AnythinkError(Exception):
    """Base exception for all Anythink errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class ConfigError(AnythinkError):
    """Raised when configuration is invalid or missing."""


class ProviderError(AnythinkError):
    """Base class for LLM provider errors."""

    def __init__(self, message: str, provider: str, user_message: str | None = None) -> None:
        super().__init__(message, user_message)
        self.provider = provider


class AuthenticationError(ProviderError):
    """Raised when an API key is invalid or missing."""


class RateLimitError(ProviderError):
    """Raised when the provider rate limit is exceeded."""


class ProviderUnavailableError(ProviderError):
    """Raised when the provider is unreachable (network error, local server down, etc.)."""


class ModelNotFoundError(ProviderError):
    """Raised when the requested model does not exist for the provider."""


class SessionError(AnythinkError):
    """Raised when a session cannot be saved, loaded, or found."""


class KeychainError(AnythinkError):
    """Raised when the OS keychain operation fails."""


class PluginError(AnythinkError):
    """Raised when a plugin cannot be loaded or is malformed."""


class SearchError(AnythinkError):
    """Raised when a web search operation fails."""


class FileError(AnythinkError):
    """Raised when a file cannot be read, is too large, or has an unsupported format."""


class RAGError(AnythinkError):
    """Raised when a RAG index cannot be built, loaded, queried, or managed."""


class ToolExecutionError(AnythinkError):
    """Raised when a tool (e.g. code execution) fails to run or returns an error."""


class BrowseError(AnythinkError):
    """Raised when an agentic web-browsing fetch fails."""


class MCPError(AnythinkError):
    """Raised when an MCP client/server operation fails."""


class VoiceError(AnythinkError):
    """Raised when voice capture or transcription fails."""


class BranchError(AnythinkError):
    """Raised when a conversation branch cannot be created, switched, or found."""


class NotificationError(AnythinkError):
    """Raised when a desktop notification cannot be delivered."""

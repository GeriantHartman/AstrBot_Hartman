from __future__ import annotations


class AstrBotError(Exception):
    """Base exception for all AstrBot errors."""


class ProviderNotFoundError(AstrBotError):
    """Raised when a specified provider is not found."""


class EmptyModelOutputError(AstrBotError):
    """Raised when the model response contains no usable assistant output."""


class LLMContentFilteredError(AstrBotError):
    """Raised when model output was blocked by the provider's content policy
    (e.g. Gemini PROHIBITED_CONTENT / SAFETY / BLOCKLIST / SPII).

    Retrying the same provider is futile for this error — callers should
    fall back to a different provider instead.
    """

    def __init__(self, provider: str = "", reason: str = "", msg: str = ""):
        super().__init__(msg or f"{provider} content filtered: {reason}")
        self.provider = provider
        self.reason = reason


class LLMTransientError(AstrBotError):
    """Raised for transient, retryable provider failures
    (e.g. 504/503/502, connection error, timeout, empty candidates).

    The provider's own retry loop will retry a bounded number of times
    with exponential backoff before propagating this exception. Callers
    seeing this exception have already exhausted same-provider retries
    and should fall back to a different provider.
    """



class KnowledgeBaseUploadError(AstrBotError):
    """Raised when knowledge base upload fails with a user-facing message."""

    def __init__(
        self,
        *,
        stage: str,
        user_message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(user_message)
        self.stage = stage
        self.user_message = user_message
        self.details = details or {}

    def __str__(self) -> str:
        return self.user_message

from __future__ import annotations

from collections.abc import Collection
from typing import Any

CUSTOM_USER_PROTOCOL_KEY = "_custom_user_protocol"


def expand_custom_user_protocol(
    messages: list[dict[str, Any]],
    *,
    provider_family: str,
) -> list[dict[str, Any]]:
    """Render provider-specific custom user protocol placeholders."""
    rendered: list[dict[str, Any]] = []
    openai_prefix: list[dict[str, Any]] = []

    for message in messages:
        config = message.get(CUSTOM_USER_PROTOCOL_KEY)
        if not isinstance(config, dict):
            rendered.append(message)
            continue

        content = message.get("content")
        if not isinstance(content, str) or not content:
            continue

        if provider_family == "openai":
            openai_config = config.get("openai", {})
            if not isinstance(openai_config, dict):
                openai_config = {}
            if openai_config.get("prepend_user_separator", True):
                openai_prefix.append(
                    {
                        "role": "user",
                        "content": str(openai_config.get("user_separator", "  \n")),
                    }
                )
            openai_prefix.append(
                {
                    "role": str(openai_config.get("role", "system") or "system"),
                    "content": content,
                }
            )
            continue

        native_config = config.get("native_top_level_system", {})
        if not isinstance(native_config, dict):
            native_config = {}
        rendered.append(
            {
                "role": str(native_config.get("role", "user") or "user"),
                "content": content,
            }
        )

    return [*openai_prefix, *rendered]


def merge_adjacent_messages(
    messages: list[dict[str, Any]],
    *,
    roles: Collection[str] | None = None,
    separator: str = "\n\n",
) -> list[dict[str, Any]]:
    """Merge adjacent messages with the same role while preserving their order."""
    merged: list[dict[str, Any]] = []
    allowed_roles = set(roles) if roles is not None else None

    for message in messages:
        current = dict(message)
        role = current.get("role")
        can_merge = (
            merged
            and role == merged[-1].get("role")
            and (allowed_roles is None or role in allowed_roles)
        )
        if can_merge:
            merged[-1]["content"] = _merge_content(
                merged[-1].get("content"),
                current.get("content"),
                separator=separator,
            )
            continue
        merged.append(current)

    return merged


def split_leading_system_messages(
    messages: list[dict[str, Any]],
    *,
    separator: str = "\n\n",
) -> tuple[str, list[dict[str, Any]]]:
    """Extract the leading system prefix for APIs with a top-level system field."""
    system_parts: list[str] = []
    split_at = 0
    for split_at, message in enumerate(messages):
        if message.get("role") != "system":
            break
        system_parts.append(_content_to_text(message.get("content")))
    else:
        split_at = len(messages)

    return separator.join(part for part in system_parts if part), messages[split_at:]


def _merge_content(left: Any, right: Any, *, separator: str) -> Any:
    if isinstance(left, str) and isinstance(right, str):
        return f"{left}{separator}{right}"
    return [*_content_to_blocks(left), *_content_to_blocks(right)]


def _content_to_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, list):
        return list(content)
    if content is None:
        return []
    return [{"type": "text", "text": str(content)}]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)

    text_parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            text_parts.append(str(part.get("text", "")))
    return "\n".join(text_parts)

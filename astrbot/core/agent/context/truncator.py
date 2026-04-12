from ..message import Message, TextPart, ThinkPart


class ContextTruncator:
    """Context truncator."""

    def _has_tool_calls(self, message: Message) -> bool:
        """Check if a message contains tool calls."""
        return (
            message.role == "assistant"
            and message.tool_calls is not None
            and len(message.tool_calls) > 0
        )

    @staticmethod
    def _split_system_rest(
        messages: list[Message],
    ) -> tuple[list[Message], list[Message]]:
        """Split messages into system messages and the rest.

        Returns:
            tuple: (system_messages, non_system_messages)
        """
        first_non_system = 0
        for i, msg in enumerate(messages):
            if msg.role != "system":
                first_non_system = i
                break
        return messages[:first_non_system], messages[first_non_system:]

    @staticmethod
    def _ensure_user_message(
        system_messages: list[Message],
        truncated: list[Message],
        original_messages: list[Message],
    ) -> list[Message]:
        """Ensure the result always contains the first user message right after
        system messages. This is required by many LLM APIs (e.g. Zhipu) that
        mandate a ``user`` message immediately following the ``system`` message.
        """
        if truncated and truncated[0].role == "user":
            return system_messages + truncated

        # Locate the first user message from the *original* list.
        first_user = next((m for m in original_messages if m.role == "user"), None)
        if first_user is None:
            return system_messages + truncated

        return system_messages + [first_user] + truncated

    def fix_messages(self, messages: list[Message]) -> list[Message]:
        """Fix the message list to ensure the validity of tool call and tool response pairing.

        This method ensures that:
        1. Each `tool` message is preceded by an `assistant` message containing `tool_calls`.
        2. Each `assistant` message containing `tool_calls` is followed by corresponding `

        This is a requirement of the OpenAI Chat Completions API specification (Gemini enforces this strictly).
        """
        if not messages:
            return messages

        fixed_messages: list[Message] = []
        pending_assistant: Message | None = None
        pending_tools: list[Message] = []

        def flush_pending_if_valid() -> None:
            nonlocal pending_assistant, pending_tools
            if pending_assistant is not None and pending_tools:
                fixed_messages.append(pending_assistant)
                fixed_messages.extend(pending_tools)
            pending_assistant = None
            pending_tools = []

        for msg in messages:
            if msg.role == "tool":
                # Only record tool responses when there is a pending assistant(tool_calls)
                if pending_assistant is not None:
                    pending_tools.append(msg)
                # Isolated tool messages without a preceding assistant(tool_calls) are ignored
                continue

            if self._has_tool_calls(msg):
                # When encountering a new assistant(tool_calls), first process the old pending chain
                flush_pending_if_valid()
                pending_assistant = msg
                continue

            # Non-tool messages that do not contain tool_calls will break the pending chain.
            # Flush any pending chain first, then append the current message normally.
            flush_pending_if_valid()
            fixed_messages.append(msg)

        # Flush the last pending chain at the end,
        # ensuring that any remaining valid assistant(tool_calls) and its tools are included in the final list.
        flush_pending_if_valid()

        return fixed_messages

    def truncate_by_turns(
        self,
        messages: list[Message],
        keep_most_recent_turns: int,
        drop_turns: int = 1,
    ) -> list[Message]:
        """
        Turn-based truncation strategy, which drops the oldest turns while keeping the most recent N turns.
        A turn consists of a user message and an assistant message.
        This method ensures that the truncated context list conforms to OpenAI's context format.

        Args:
            messages: The original list of messages in the context.
            keep_most_recent_turns: The number of most recent turns to keep. If set to -1, it means keeping all turns (no truncation).
            drop_turns: The number of turns to drop from the beginning.

        Returns:
            The truncated list of messages.
        """
        if keep_most_recent_turns == -1:
            return messages

        system_messages, non_system_messages = self._split_system_rest(messages)

        if len(non_system_messages) // 2 <= keep_most_recent_turns:
            return messages

        num_to_keep = keep_most_recent_turns - drop_turns + 1
        if num_to_keep <= 0:
            truncated_contexts = []
        else:
            truncated_contexts = non_system_messages[-num_to_keep * 2 :]

        # Find the first user message
        index = next(
            (i for i, item in enumerate(truncated_contexts) if item.role == "user"),
            None,
        )
        if index is not None and index > 0:
            truncated_contexts = truncated_contexts[index:]

        result = self._ensure_user_message(
            system_messages, truncated_contexts, messages
        )
        return self.fix_messages(result)

    def truncate_by_dropping_oldest_turns(
        self,
        messages: list[Message],
        drop_turns: int = 1,
    ) -> list[Message]:
        """Drop the oldest N turns, regardless of the number of turns to keep."""
        if drop_turns <= 0:
            return messages

        system_messages, non_system_messages = self._split_system_rest(messages)

        if len(non_system_messages) // 2 <= drop_turns:
            truncated_non_system = []
        else:
            truncated_non_system = non_system_messages[drop_turns * 2 :]

        # Find the first user message
        index = next(
            (i for i, item in enumerate(truncated_non_system) if item.role == "user"),
            None,
        )
        if index is not None:
            truncated_non_system = truncated_non_system[index:]

        result = self._ensure_user_message(
            system_messages, truncated_non_system, messages
        )
        return self.fix_messages(result)

    def truncate_by_halving(
        self,
        messages: list[Message],
    ) -> list[Message]:
        """Halve the number of messages, keeping the most recent ones."""
        if len(messages) <= 2:
            return messages

        system_messages, non_system_messages = self._split_system_rest(messages)

        messages_to_delete = len(non_system_messages) // 2
        if messages_to_delete == 0:
            return messages

        truncated_non_system = non_system_messages[messages_to_delete:]

        # Find the first user message
        index = next(
            (i for i, item in enumerate(truncated_non_system) if item.role == "user"),
            None,
        )
        if index is not None:
            truncated_non_system = truncated_non_system[index:]

        result = self._ensure_user_message(
            system_messages, truncated_non_system, messages
        )
        return self.fix_messages(result)

    def compress_old_turns(
        self,
        messages: list[Message],
        keep_recent_turns: int = 3,
        batch_size: int = 5,
    ) -> list[Message]:
        """Aggressively compress old turns for token savings and attention quality.

        For turns older than the staircase cutoff:
          - Remove entire tool call chains (assistant(tool_calls) + tool messages)
          - Strip reasoning/ThinkPart from final assistant messages
          - Keep only: user messages + assistant narrative (plain text)

        For recent turns (within keep_recent_turns):
          - Keep full tool chains
          - Strip reasoning from intermediate tool-calling steps only (always-on,
            since CoT for tool selection is never useful post-call)

        Staircase boundary: cutoff advances in jumps of ``batch_size`` turns,
        so the prefix stays stable for ``batch_size`` turns between jumps,
        preserving LLM API prefix-cache hits.

        Args:
            messages: The message list.
            keep_recent_turns: Minimum number of recent turns to keep uncompressed.
            batch_size: Staircase step size. Cutoff moves every batch_size turns.
                Set to 1 for a sliding window (no staircase).

        Returns:
            Compressed message list.
        """
        turn_indices = [i for i, m in enumerate(messages) if m.role == "user"]
        total_turns = len(turn_indices)

        if total_turns <= keep_recent_turns:
            return messages

        # Staircase: round down compressible turns to nearest batch_size
        compressible = total_turns - keep_recent_turns
        compressed_count = (compressible // batch_size) * batch_size
        if compressed_count <= 0:
            return messages

        cutoff_index = turn_indices[compressed_count]

        result: list[Message] = []
        i = 0
        while i < len(messages):
            msg = messages[i]

            if i < cutoff_index:
                # --- Old region: aggressive compression ---
                if self._has_tool_calls(msg):
                    # Skip assistant(tool_calls) + subsequent tool results
                    i += 1
                    while i < len(messages) and messages[i].role == "tool":
                        i += 1
                    continue
                if msg.role == "tool":
                    # Orphaned tool message
                    i += 1
                    continue
                if msg.role == "assistant":
                    result.append(self._strip_reasoning(msg))
                    i += 1
                    continue
                # user / system: keep as-is
                result.append(msg)
                i += 1
            else:
                # --- Recent region: keep full, strip intermediate reasoning ---
                if self._has_tool_calls(msg):
                    result.append(self._strip_reasoning(msg))
                else:
                    result.append(msg)
                i += 1

        return result

    @staticmethod
    def _strip_reasoning(msg: Message) -> Message:
        """Strip reasoning/ThinkPart from an assistant message.

        Handles both fully-deserialized ThinkPart objects and raw dicts
        (``{"type": "think", ...}``) that may appear when messages are
        loaded directly from the database JSON.
        """
        content = msg.content
        if not isinstance(content, list):
            return msg

        kept = []
        for part in content:
            if isinstance(part, ThinkPart):
                continue
            if isinstance(part, dict) and part.get("type") == "think":
                continue
            kept.append(part)

        if len(kept) == len(content):
            return msg  # nothing stripped

        # Simplify single-text-part lists back to a plain string
        if len(kept) == 0:
            new_content: str | list = ""
        elif len(kept) == 1:
            p = kept[0]
            if isinstance(p, TextPart):
                new_content = p.text
            elif isinstance(p, dict) and p.get("type") == "text":
                new_content = p.get("text", "")
            else:
                new_content = kept
        else:
            new_content = kept

        return Message(
            role=msg.role,
            content=new_content,
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
        )

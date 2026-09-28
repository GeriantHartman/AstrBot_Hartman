from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_nsfw_mode"
SNAPSHOT_KEY = "nsfw_mode_request_snapshot"
ENTER_MARKER = "[NSFW_MODE_ENTER]"
EXIT_MARKER = "[NSFW_MODE_EXIT]"
SUMMARY_MARKER = "[NSFW_MODE_SUMMARY]"

DEFAULT_SUMMARY_SYSTEM_PROMPT = f"""你是一个对话上下文折叠模块。

你收到的内容已经由程序根据 {ENTER_MARKER} 和 {EXIT_MARKER} 标记精确截取。
不要判断哪些部分需要总结，不要扩大范围，也不要缩小范围。
你的唯一任务是把输入片段替换成一段“无细节的高层连续性摘要”。

硬性规则：
- 只用中文输出。
- 不保留露骨、身体、动作、感官、具体对白或成人细节。
- 不引用原文句子。
- 只保留连续性事实：参与者、关系变化、情绪变化、决定、承诺、场景状态、未解决伏笔、角色长期状态。
- 如果年龄、同意、强迫或安全边界存在模糊内容，省略该模糊内容，只写中性的剧情状态变化。
- 只输出替换用摘要，不要解释你的处理过程。
- 摘要必须以 {SUMMARY_MARKER} 开头。
- 摘要通常控制在 80-220 个中文字符。
"""

DEFAULT_SUMMARY_USER_TEMPLATE = """以下是程序已经根据 NSFW enter/exit 标记截取好的固定片段。
不要判断总结范围；只总结下面这段内容。

请把它折叠为中文高层连续性摘要，用于替换原文进入长期上下文。
必须删除具体对白、动作、感官、身体和成人细节，只保留“发生了什么”的事实层结果、关系变化、情绪变化、场景状态和未解决伏笔。

固定片段原文：
{conversation_text}
"""

ERROR_PATTERNS = (
    "LLM 请求失败",
    "Provider 请求失败",
    "Content Filter",
    "PROHIBITED_CONTENT",
    "finish reason",
    "被内容过滤",
    "内容安全",
    "LLMContentFilteredError",
    "LLMTransientError",
)


@dataclass
class SessionState:
    session_open: bool = False
    active: bool = False
    segment_start: int = -1
    conversation_id: str = ""


@register(
    PLUGIN_NAME,
    "Hartman",
    "Session-scoped NSFW mode with isolated style, provider override, fallback, and exit summary compaction",
    "0.1.0",
    "",
)
class NsfwModePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            data_root = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] cannot resolve AstrBot data path: {exc}")
            data_root = Path("data/plugin_data") / PLUGIN_NAME

        data_root.mkdir(parents=True, exist_ok=True)
        self._data_root = data_root
        self._payload_log_dir = data_root / "llm_payload_logs"
        self._state_file = data_root / "session_state.json"
        self._states: dict[str, SessionState] = self._load_states()
        self._style_file = (
            Path(__file__).resolve().parent / "skills" / "nsfw-mode" / "SKILL.md"
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def _enabled(self) -> bool:
        return self._as_bool(self.config.get("enabled", True))

    @property
    def _default_session_open(self) -> bool:
        return self._as_bool(self.config.get("default_session_open", False))

    @property
    def _inject_header(self) -> str:
        return str(self.config.get("inject_header", "## NSFW Mode") or "").strip()

    @property
    def _pre_system_user_content(self) -> str:
        return self._raw_config_text("pre_system_user_content")

    @property
    def _pre_system_system_content(self) -> str:
        return self._raw_config_text("pre_system_system_content")

    @property
    def _pre_system_inject_on_open(self) -> bool:
        return self._as_bool(self.config.get("pre_system_inject_on_open", True))

    @property
    def _payload_log_enabled(self) -> bool:
        return self._as_bool(self.config.get("enable_payload_log", False))

    @property
    def _payload_log_max_files(self) -> int:
        try:
            return max(1, int(self.config.get("payload_log_max_files", 200)))
        except Exception:  # noqa: BLE001
            return 200

    @property
    def _use_independent_provider(self) -> bool:
        return self._as_bool(self.config.get("use_independent_provider", False))

    @property
    def _nsfw_provider_id(self) -> str:
        return str(self.config.get("nsfw_provider_id", "") or "").strip()

    @property
    def _fallback_min_chars(self) -> int:
        try:
            return max(0, int(self.config.get("fallback_min_chars", 5)))
        except Exception:  # noqa: BLE001
            return 5

    @property
    def _error_fallback_enabled(self) -> bool:
        return self._as_bool(self.config.get("error_fallback_enabled", True))

    @property
    def _summary_system_prompt(self) -> str:
        custom = str(self.config.get("summary_system_prompt", "") or "").strip()
        if custom:
            if "You are a context compaction module." in custom:
                return DEFAULT_SUMMARY_SYSTEM_PROMPT
            return custom
        return DEFAULT_SUMMARY_SYSTEM_PROMPT

    @property
    def _summary_user_template(self) -> str:
        custom = str(self.config.get("summary_user_template", "") or "").strip()
        if custom:
            if "请将下面从 /nsfw enter 到 /nsfw exit 之间的对话原文折叠" in custom:
                return DEFAULT_SUMMARY_USER_TEMPLATE
            return custom
        return DEFAULT_SUMMARY_USER_TEMPLATE

    @property
    def _summary_max_chars(self) -> int:
        try:
            return max(120, int(self.config.get("summary_max_chars", 800)))
        except Exception:  # noqa: BLE001
            return 800

    @staticmethod
    def _as_bool(raw: Any) -> bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(raw)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_states(self) -> dict[str, SessionState]:
        try:
            if not self._state_file.exists():
                return {}
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            states: dict[str, SessionState] = {}
            for session_id, payload in raw.items():
                if not isinstance(payload, dict):
                    continue
                states[str(session_id)] = SessionState(
                    session_open=self._as_bool(payload.get("session_open", False)),
                    active=self._as_bool(payload.get("active", False)),
                    segment_start=int(payload.get("segment_start", -1) or -1),
                    conversation_id=str(payload.get("conversation_id", "") or ""),
                )
            return states
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to load session state: {exc}")
            return {}

    def _save_states(self) -> None:
        try:
            payload = {
                session_id: asdict(state) for session_id, state in self._states.items()
            }
            self._state_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to save session state: {exc}")

    def _state_for(self, session_id: str) -> SessionState:
        state = self._states.get(session_id)
        if state is None:
            state = SessionState(session_open=self._default_session_open)
            self._states[session_id] = state
        return state

    def _save_state_for(self, session_id: str, state: SessionState) -> None:
        self._states[session_id] = state
        self._save_states()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @filter.command_group("nsfw")
    def nsfw_group(self):
        """NSFW mode management."""

    @nsfw_group.command("help")
    async def nsfw_help(self, event: AstrMessageEvent):
        lines = [
            "NSFW Mode 命令：",
            "  /nsfw help - 显示本帮助",
            "  /nsfw status - 查看当前 session 状态和 provider 配置",
            "  /nsfw open - 开启本 session 的 NSFW 功能入口，但不进入 NSFW 段",
            "  /nsfw close - 关闭本 session 的 NSFW 功能；若正在 NSFW 段内，会先立即 exit 并 summary",
            "  /nsfw enter - 进入 NSFW 段：开始注入独立 NSFW style，并按配置切换 NSFW provider",
            "  /nsfw exit - 退出 NSFW 段：把 enter 到 exit 之间的历史交给 NSFW provider summary，并用 summary 替换原文",
            "",
            "配置说明：pre_system_inject_on_open=true 时，/nsfw open 后就会注入自定义 role=user 与 role=system；/nsfw enter 后才会注入 NSFW style 与切换 provider。",
            f"payload 调试日志目录：{self._payload_log_dir}",
            "设计说明：本插件不使用触发词；只有 /nsfw enter 会进入 NSFW 段。exit 没有 5 轮 pending，会立刻折叠当前段历史。",
        ]
        yield event.plain_result("\n".join(lines)).stop_event()

    @nsfw_group.command("open")
    async def nsfw_open(self, event: AstrMessageEvent):
        if not self._enabled:
            yield event.plain_result("插件配置 enabled=false，无法开启。").stop_event()
            return
        session_id = event.unified_msg_origin
        state = self._state_for(session_id)
        if state.session_open:
            yield event.plain_result(
                "本 session 的 NSFW 功能入口已经开启。"
            ).stop_event()
            return
        state.session_open = True
        self._save_state_for(session_id, state)
        yield event.plain_result(
            "已开启本 session 的 NSFW 功能入口。使用 /nsfw enter 进入 NSFW 段。"
        ).stop_event()

    @nsfw_group.command("close")
    async def nsfw_close(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin
        state = self._state_for(session_id)
        messages: list[str] = []
        if state.active:
            messages.append(await self._exit_active_segment(session_id))
            state = self._state_for(session_id)
        if not state.session_open:
            yield event.plain_result(
                "本 session 的 NSFW 功能入口已经关闭。"
            ).stop_event()
            return
        state.session_open = False
        state.active = False
        state.segment_start = -1
        state.conversation_id = ""
        self._save_state_for(session_id, state)
        messages.append("已关闭本 session 的 NSFW 功能入口。")
        yield event.plain_result("\n".join(messages)).stop_event()

    @nsfw_group.command("enter")
    async def nsfw_enter(self, event: AstrMessageEvent):
        if not self._enabled:
            yield event.plain_result(
                "插件配置 enabled=false，无法进入 NSFW 模式。"
            ).stop_event()
            return

        session_id = event.unified_msg_origin
        state = self._state_for(session_id)
        if state.active:
            yield event.plain_result("当前已经处于 NSFW 段内。").stop_event()
            return

        conversation_id, _history, enter_index = await self._append_marker(
            session_id,
            ENTER_MARKER,
        )
        state.session_open = True
        state.active = True
        state.segment_start = enter_index
        state.conversation_id = conversation_id
        self._save_state_for(session_id, state)

        provider_chain = await self._resolved_nsfw_provider_chain(session_id)
        self._log_provider_chain("enter", session_id, provider_chain)
        provider_line = self._format_provider_status_line(provider_chain)
        yield event.plain_result(
            "已进入 NSFW 段。之后的 LLM 请求会注入独立 NSFW style。"
            f"\n已写入 enter 标记：{ENTER_MARKER}"
            f"\n{provider_line}"
            "\n使用 /nsfw exit 会写入 exit 标记，然后只总结两个标记之间的内容。"
        ).stop_event()

    @nsfw_group.command("exit")
    async def nsfw_exit(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin
        state = self._state_for(session_id)
        if not state.active:
            yield event.plain_result("当前没有处于 NSFW 段内。").stop_event()
            return
        yield event.plain_result(
            await self._exit_active_segment(session_id)
        ).stop_event()

    @nsfw_group.command("status")
    async def nsfw_status(self, event: AstrMessageEvent):
        session_id = event.unified_msg_origin
        state = self._state_for(session_id)
        provider_line = await self._provider_status_line(session_id)
        lines = [
            f"插件配置：{'启用' if self._enabled else '关闭'}",
            f"本 session 功能入口：{'开启' if state.session_open else '关闭'}",
            f"当前 NSFW 段：{'进行中' if state.active else '未进入'}",
            f"enter marker index：{state.segment_start if state.active else '无'}",
            f"conversation_id：{state.conversation_id or '当前会话'}",
            provider_line,
            f"独立 provider 开关：{'开启' if self._use_independent_provider else '关闭'}",
            f"fallback 最小字符阈值：{self._fallback_min_chars}",
            f"open 后预注入：{'开启' if self._pre_system_inject_on_open else '关闭'}",
            f"payload 调试日志：{'开启' if self._payload_log_enabled else '关闭'}",
            f"payload 调试日志目录：{self._payload_log_dir}",
        ]
        yield event.plain_result("\n".join(lines)).stop_event()

    # ------------------------------------------------------------------
    # Hooks: provider selection, style injection, fallback
    # ------------------------------------------------------------------

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent) -> None:
        if not self._is_active(event.unified_msg_origin):
            return
        if not self._use_independent_provider:
            return
        target = self._nsfw_provider_id
        if not target:
            return
        try:
            event.set_extra("selected_provider", target)
            logger.info(
                f"[nsfw_mode] selected independent NSFW provider '{target}' "
                f"for {event.unified_msg_origin}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to set selected_provider: {exc}")

    @filter.on_llm_request()
    async def on_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        session_id = event.unified_msg_origin
        active = self._is_active(session_id)
        should_pre_inject = self._should_inject_pre_system(session_id)
        if not active and not should_pre_inject:
            return

        if should_pre_inject:
            self._inject_pre_system_messages(req)

        provider_id = str(event.get_extra("selected_provider") or "").strip()
        provider_chain: list[str] = []
        fallback_chain: list[str] = []
        if active:
            style_text = self._nsfw_style_text()
            if style_text:
                header = self._inject_header
                injected = f"{header}\n{style_text}" if header else style_text
                req.system_prompt = (
                    (req.system_prompt or "").rstrip() + "\n\n" + injected
                )

            if not provider_id:
                provider_id = await self._current_provider_id(session_id)
            provider_chain = await self._resolved_nsfw_provider_chain(session_id)
            fallback_chain = [pid for pid in provider_chain if pid != provider_id]
            logger.info(
                f"[nsfw_mode] request provider: session={session_id}, "
                f"provider='{provider_id or 'unresolved'}', fallback={fallback_chain}"
            )
            event.set_extra(
                SNAPSHOT_KEY,
                {
                    "prompt": req.prompt,
                    "system_prompt": req.system_prompt,
                    "contexts": req.contexts or [],
                    "provider_id": provider_id,
                },
            )

        await self._write_payload_log(
            event,
            req,
            active=active,
            pre_system_injected=should_pre_inject,
            provider_id=provider_id,
            provider_chain=provider_chain,
            fallback_chain=fallback_chain,
        )

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse) -> None:
        if not self._is_active(event.unified_msg_origin):
            return
        if not self._use_independent_provider:
            return

        text = str(resp.completion_text or "").strip()
        if len(text) >= self._fallback_min_chars:
            return

        fallback = await self._generate_live_fallback(event, reason="empty response")
        if fallback:
            resp.completion_text = fallback

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        if not self._is_active(event.unified_msg_origin):
            return
        if not self._use_independent_provider or not self._error_fallback_enabled:
            return

        result = event.get_result()
        if result is None or not result.chain:
            return
        text = result.get_plain_text(with_other_comps_mark=True)
        if not self._looks_like_provider_error(text):
            return

        fallback = await self._generate_live_fallback(event, reason="provider error")
        if not fallback:
            return

        from astrbot.core.message.components import Plain

        result.chain = [Plain(fallback)]
        event.set_result(result)

    # ------------------------------------------------------------------
    # Mode and summary logic
    # ------------------------------------------------------------------

    def _is_active(self, session_id: str) -> bool:
        if not self._enabled:
            return False
        state = self._state_for(session_id)
        return state.session_open and state.active

    def _is_session_open(self, session_id: str) -> bool:
        if not self._enabled:
            return False
        return self._state_for(session_id).session_open

    def _should_inject_pre_system(self, session_id: str) -> bool:
        if self._is_active(session_id):
            return True
        return self._pre_system_inject_on_open and self._is_session_open(session_id)

    async def _exit_active_segment(self, session_id: str) -> str:
        state = self._state_for(session_id)
        conversation_id, history, exit_index = await self._append_marker(
            session_id,
            EXIT_MARKER,
            conversation_id=state.conversation_id,
        )
        bounds = self._locate_marker_bounds(
            history,
            enter_hint=state.segment_start,
            exit_hint=exit_index,
        )
        if bounds:
            enter_index, exit_index = bounds
            segment_start = enter_index + 1
            replace_start = enter_index
            replace_end = exit_index + 1
        else:
            logger.warning(
                f"[nsfw_mode] marker bounds missing for {session_id}; "
                "falling back to saved segment_start"
            )
            exit_index = self._find_last_marker(history, EXIT_MARKER)
            if exit_index < 0:
                exit_index = len(history)
                replace_end = len(history)
            else:
                replace_end = exit_index + 1
            segment_start = max(0, min(state.segment_start, exit_index))
            replace_start = segment_start
        segment = history[segment_start:exit_index]

        summary_note = ""
        if conversation_id:
            try:
                if segment:
                    summary = await self._summarize_segment(session_id, segment)
                    summary_note = "summary 已由 NSFW provider 生成。"
                else:
                    summary = self._local_summary(segment)
                    summary_note = "两个标记之间没有新增内容，已写入空段摘要。"
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[nsfw_mode] summary provider failed; using local fallback: {exc}",
                    exc_info=True,
                )
                summary = self._local_summary(segment)
                summary_note = "summary provider 调用失败，已使用本地无细节兜底摘要。"

            new_history = (
                history[:replace_start]
                + [{"role": "assistant", "content": summary}]
                + history[replace_end:]
            )
            await self.context.conversation_manager.update_conversation(
                unified_msg_origin=session_id,
                conversation_id=conversation_id,
                history=new_history,
            )
            detail = (
                f"已删除 {ENTER_MARKER} 与 {EXIT_MARKER} 之间的 "
                f"{len(segment)} 条历史，并替换为 1 条 summary。"
            )
        else:
            detail = "没有找到可写回的对话，未能折叠历史。"

        state.active = False
        state.segment_start = -1
        state.conversation_id = ""
        self._save_state_for(session_id, state)
        return f"已退出 NSFW 段。{detail}{(' ' + summary_note) if summary_note else ''}"

    async def _summarize_segment(
        self,
        session_id: str,
        segment: list[dict[str, Any]],
    ) -> str:
        conversation_text = self._format_segment(segment)
        if not conversation_text.strip():
            return self._local_summary(segment)

        prompt_template = self._summary_user_template
        if "{conversation_text}" in prompt_template:
            prompt = prompt_template.replace("{conversation_text}", conversation_text)
        else:
            prompt = prompt_template.rstrip() + "\n\n" + conversation_text

        chain = await self._resolved_nsfw_provider_chain(session_id)
        if not chain:
            raise RuntimeError("No NSFW provider available for summary")

        response = await self._call_provider_chain(
            chain,
            prompt=prompt,
            system_prompt=self._summary_system_prompt,
            contexts=[],
            purpose="summary",
        )
        summary = self._normalize_summary(response.completion_text)
        if not summary:
            raise RuntimeError("NSFW summary provider returned empty text")
        return summary

    def _normalize_summary(self, text: Any) -> str:
        summary = str(text or "").strip()
        if summary.startswith("```"):
            summary = summary.strip("`").strip()
        if not summary:
            return ""
        if not summary.startswith(SUMMARY_MARKER):
            summary = f"{SUMMARY_MARKER}\n{summary}"
        if len(summary) > self._summary_max_chars:
            summary = summary[: self._summary_max_chars].rstrip() + "..."
        return summary

    def _local_summary(self, segment: list[dict[str, Any]]) -> str:
        user_count = 0
        assistant_count = 0
        for msg in segment:
            if self._is_any_marker_message(msg):
                continue
            role = str(msg.get("role", "")).lower()
            if role == "user":
                user_count += 1
            elif role == "assistant":
                assistant_count += 1
        return (
            f"{SUMMARY_MARKER}\n"
            "此前 NSFW 段的原文已折叠。该段包含 "
            f"{user_count} 条用户消息与 {assistant_count} 条助手回复；"
            "只保留一段成人/私密向互动发生过，并对关系、情绪或剧情状态产生影响这一高层事实，"
            "具体对白、动作、身体、感官和露骨细节已移除。"
        )

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    async def _provider_status_line(self, session_id: str) -> str:
        chain = await self._resolved_nsfw_provider_chain(session_id)
        return self._format_provider_status_line(chain)

    def _format_provider_status_line(self, chain: list[str]) -> str:
        if not chain:
            return "NSFW provider：未解析到可用 provider"
        mode = "独立配置" if self._use_independent_provider else "当前主 provider"
        return f"NSFW provider：{chain[0]}（{mode}）; fallback：{', '.join(chain[1:]) or '无'}"

    def _log_provider_chain(
        self,
        action: str,
        session_id: str,
        provider_chain: list[str],
    ) -> None:
        primary = provider_chain[0] if provider_chain else ""
        fallbacks = provider_chain[1:] if len(provider_chain) > 1 else []
        logger.info(
            f"[nsfw_mode] {action}: session={session_id}, "
            f"provider='{primary or 'unresolved'}', fallback={fallbacks}, "
            f"independent_provider={self._use_independent_provider}"
        )

    async def _current_provider_id(self, session_id: str) -> str:
        try:
            return await self.context.get_current_chat_provider_id(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] cannot resolve current provider: {exc}")
            return ""

    async def _resolved_nsfw_provider_chain(self, session_id: str) -> list[str]:
        primary = self._nsfw_provider_id if self._use_independent_provider else ""
        if not primary:
            primary = await self._current_provider_id(session_id)

        chain: list[str] = []
        if primary:
            chain.append(primary)
        if self._use_independent_provider:
            for provider_id in self._split_chain(
                self.config.get("nsfw_provider_chain", [])
            ):
                if provider_id not in chain:
                    chain.append(provider_id)
        return chain

    async def _call_provider_chain(
        self,
        provider_chain: list[str],
        *,
        prompt: str | None,
        system_prompt: str,
        contexts: list[dict[str, Any]],
        purpose: str,
    ) -> LLMResponse:
        last_exc: Exception | None = None
        for index, provider_id in enumerate(provider_chain):
            try:
                if index > 0:
                    logger.warning(
                        f"[nsfw_mode] {purpose}: switching to fallback provider "
                        f"'{provider_id}'"
                    )
                response = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                    contexts=contexts,
                    system_prompt=system_prompt,
                )
                if str(response.completion_text or "").strip():
                    if index > 0 or purpose.startswith("live fallback"):
                        logger.warning(
                            f"[nsfw_mode] {purpose}: fallback provider used "
                            f"provider='{provider_id}'"
                        )
                    else:
                        logger.info(
                            f"[nsfw_mode] {purpose}: provider used "
                            f"provider='{provider_id}'"
                        )
                    return response
                last_exc = RuntimeError(
                    f"{purpose}: provider '{provider_id}' returned empty text"
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    f"[nsfw_mode] {purpose}: provider '{provider_id}' failed: {exc}"
                )
        raise last_exc or RuntimeError(f"{purpose}: provider chain exhausted")

    async def _generate_live_fallback(
        self, event: AstrMessageEvent, *, reason: str
    ) -> str:
        snapshot = event.get_extra(SNAPSHOT_KEY)
        if not isinstance(snapshot, dict):
            return ""
        session_id = event.unified_msg_origin
        provider_chain = await self._resolved_nsfw_provider_chain(session_id)
        failed_provider = str(snapshot.get("provider_id", "") or "").strip()
        fallback_chain = [
            provider_id
            for provider_id in provider_chain
            if provider_id and provider_id != failed_provider
        ]
        if not fallback_chain:
            return ""
        try:
            response = await self._call_provider_chain(
                fallback_chain,
                prompt=snapshot.get("prompt"),
                system_prompt=str(snapshot.get("system_prompt", "") or ""),
                contexts=list(snapshot.get("contexts") or []),
                purpose=f"live fallback ({reason})",
            )
            logger.warning(
                f"[nsfw_mode] live fallback completed: session={session_id}, "
                f"failed_provider='{failed_provider or 'unknown'}', "
                f"fallback_candidates={fallback_chain}"
            )
            return str(response.completion_text or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] live fallback failed: {exc}")
            return ""

    @staticmethod
    def _split_chain(raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        if isinstance(raw, str):
            return [item.strip() for item in raw.split(",") if item.strip()]
        return []

    @staticmethod
    def _looks_like_provider_error(text: str) -> bool:
        folded = " ".join(str(text or "").split())
        if not folded:
            return False
        return any(pattern.lower() in folded.lower() for pattern in ERROR_PATTERNS)

    # ------------------------------------------------------------------
    # Conversation and style helpers
    # ------------------------------------------------------------------

    async def _append_marker(
        self,
        session_id: str,
        marker: str,
        *,
        conversation_id: str = "",
    ) -> tuple[str, list[dict[str, Any]], int]:
        cid, history = await self._get_or_create_history(session_id, conversation_id)
        history.append(self._marker_message(marker))
        await self.context.conversation_manager.update_conversation(
            unified_msg_origin=session_id,
            conversation_id=cid,
            history=history,
        )
        marker_index = len(history) - 1
        logger.info(
            f"[nsfw_mode] marker appended: session={session_id}, "
            f"conversation_id={cid}, marker={marker}, index={marker_index}"
        )
        return cid, history, marker_index

    async def _get_or_create_history(
        self,
        session_id: str,
        conversation_id: str = "",
    ) -> tuple[str, list[dict[str, Any]]]:
        cid, history = await self._get_history(session_id, conversation_id)
        if cid:
            return cid, history
        cid = await self.context.conversation_manager.new_conversation(session_id)
        return cid, []

    async def _get_history(
        self,
        session_id: str,
        conversation_id: str = "",
    ) -> tuple[str, list[dict[str, Any]]]:
        conv_mgr = self.context.conversation_manager
        cid = (
            conversation_id or await conv_mgr.get_curr_conversation_id(session_id) or ""
        )
        if not cid:
            return "", []
        conv = await conv_mgr.get_conversation(
            session_id,
            cid,
            create_if_not_exists=False,
        )
        if not conv:
            return cid, []
        try:
            raw_history = conv.history
            if isinstance(raw_history, str):
                history = json.loads(raw_history) if raw_history.strip() else []
            elif isinstance(raw_history, list):
                history = raw_history
            else:
                history = []
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to parse conversation history: {exc}")
            history = []
        return cid, [item for item in history if isinstance(item, dict)]

    def _format_segment(self, segment: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for index, msg in enumerate(segment, start=1):
            if self._is_any_marker_message(msg):
                continue
            role = str(msg.get("role", "unknown") or "unknown")
            content = self._content_to_text(msg.get("content"))
            if not content:
                continue
            parts.append(f"[{index}] {role}: {content}")
        return "\n\n".join(parts)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(str(item.get("text", "") or ""))
                    elif item.get("type"):
                        texts.append(f"[{item.get('type')}]")
                elif item:
                    texts.append(str(item))
            return "\n".join(text.strip() for text in texts if text and text.strip())
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            return str(content)

    @staticmethod
    def _marker_message(marker: str) -> dict[str, str]:
        return {"role": "system", "content": marker}

    def _locate_marker_bounds(
        self,
        history: list[dict[str, Any]],
        *,
        enter_hint: int = -1,
        exit_hint: int = -1,
    ) -> tuple[int, int] | None:
        exit_index = -1
        if 0 <= exit_hint < len(history) and self._is_marker_message(
            history[exit_hint],
            EXIT_MARKER,
        ):
            exit_index = exit_hint
        else:
            exit_index = self._find_last_marker(history, EXIT_MARKER)
        if exit_index < 0:
            return None

        if 0 <= enter_hint < exit_index and self._is_marker_message(
            history[enter_hint], ENTER_MARKER
        ):
            return enter_hint, exit_index

        for index in range(exit_index - 1, -1, -1):
            if self._is_marker_message(history[index], ENTER_MARKER):
                return index, exit_index
        return None

    def _find_last_marker(self, history: list[dict[str, Any]], marker: str) -> int:
        for index in range(len(history) - 1, -1, -1):
            if self._is_marker_message(history[index], marker):
                return index
        return -1

    def _is_any_marker_message(self, msg: dict[str, Any]) -> bool:
        return self._is_marker_message(msg, ENTER_MARKER) or self._is_marker_message(
            msg,
            EXIT_MARKER,
        )

    def _is_marker_message(self, msg: dict[str, Any], marker: str) -> bool:
        return self._content_to_text(msg.get("content")).strip() == marker

    def _inject_pre_system_messages(self, req: ProviderRequest) -> None:
        contexts = list(req.contexts or [])
        removed = self._strip_pre_system_injections(contexts)
        injected: list[dict[str, Any]] = []
        user_content = self._pre_system_user_content
        system_content = self._pre_system_system_content

        if user_content != "":
            injected.append(self._pre_system_message("user", user_content))
        if system_content != "":
            injected.append(self._pre_system_message("system", system_content))
        if not injected:
            req.contexts = contexts
            if removed:
                logger.info(
                    "[nsfw_mode] removed stale pre-system context messages: "
                    f"removed={removed}, contexts_count={len(req.contexts)}"
                )
            return

        req.contexts = injected + contexts
        logger.info(
            "[nsfw_mode] injected pre-system context messages: "
            f"user={user_content != ''}, system={system_content != ''}, "
            f"removed_stale={removed}, contexts_count={len(req.contexts)}"
        )

    @staticmethod
    def _pre_system_message(role: str, content: str) -> dict[str, Any]:
        return {
            "role": role,
            "content": content,
            "_no_save": True,
            "_no_truncate": True,
        }

    def _strip_pre_system_injections(self, contexts: list[dict[str, Any]]) -> int:
        if not contexts:
            return 0

        user_content = self._pre_system_user_content
        system_content = self._pre_system_system_content
        removed = 0
        while contexts:
            msg = contexts[0]
            if not isinstance(msg, dict):
                break
            if self._is_pre_system_injection(msg, user_content, system_content):
                contexts.pop(0)
                removed += 1
                continue
            break
        return removed

    @staticmethod
    def _is_pre_system_injection(
        msg: dict[str, Any],
        user_content: str,
        system_content: str,
    ) -> bool:
        role = str(msg.get("role", "") or "").lower()
        content = msg.get("content")
        if role == "user" and user_content != "" and content == user_content:
            return True
        if role == "system" and system_content != "" and content == system_content:
            return True
        return False

    async def _write_payload_log(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        *,
        active: bool,
        pre_system_injected: bool,
        provider_id: str,
        provider_chain: list[str],
        fallback_chain: list[str],
    ) -> None:
        if not self._payload_log_enabled:
            return

        try:
            if not provider_id:
                provider_id = await self._current_provider_id(event.unified_msg_origin)
            if not provider_chain:
                provider_chain = await self._resolved_nsfw_provider_chain(
                    event.unified_msg_origin
                )
            if not fallback_chain:
                fallback_chain = [pid for pid in provider_chain if pid != provider_id]

            state = self._state_for(event.unified_msg_origin)
            payload = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "plugin": PLUGIN_NAME,
                "session_id": event.unified_msg_origin,
                "event": {
                    "message_str": str(getattr(event, "message_str", "") or ""),
                    "selected_provider_extra": str(
                        event.get_extra("selected_provider") or ""
                    ),
                },
                "nsfw_mode": {
                    "session_open": state.session_open,
                    "active": active,
                    "segment_start": state.segment_start,
                    "conversation_id": state.conversation_id,
                    "pre_system_injected": pre_system_injected,
                    "pre_system_inject_on_open": self._pre_system_inject_on_open,
                    "independent_provider": self._use_independent_provider,
                },
                "provider": {
                    "used_provider": provider_id or "",
                    "resolved_chain": provider_chain,
                    "fallback_candidates": fallback_chain,
                },
                "provider_request": self._provider_request_snapshot(req),
                "assembled_messages_preview": self._assembled_messages_preview(req),
                "notes": [
                    "AstrBot runner inserts provider_request.system_prompt as messages[0] when it is non-empty.",
                    "Plugin pre-system messages are inserted at the head of provider_request.contexts before previous conversation contexts.",
                    "Multimodal preview keeps original image/audio references; the provider runner may encode them before sending.",
                ],
            }

            self._payload_log_dir.mkdir(parents=True, exist_ok=True)
            path = self._payload_log_dir / self._payload_log_filename(
                event.unified_msg_origin
            )
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[nsfw_mode] wrote LLM payload snapshot: {path}")
            self._cleanup_payload_logs()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to write payload log: {exc}")

    def _provider_request_snapshot(self, req: ProviderRequest) -> dict[str, Any]:
        conversation = getattr(req, "conversation", None)
        conversation_id = str(getattr(conversation, "cid", "") or "")
        return {
            "prompt": req.prompt,
            "session_id": req.session_id,
            "image_urls": list(req.image_urls or []),
            "audio_urls": list(req.audio_urls or []),
            "extra_user_content_parts": self._jsonable(
                list(req.extra_user_content_parts or [])
            ),
            "func_tool": repr(req.func_tool) if req.func_tool is not None else None,
            "contexts": self._jsonable(list(req.contexts or [])),
            "system_prompt": req.system_prompt,
            "conversation_id": conversation_id,
            "tool_calls_result": self._jsonable(req.tool_calls_result),
            "model": req.model,
        }

    def _assembled_messages_preview(
        self,
        req: ProviderRequest,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        messages.extend(self._jsonable(list(req.contexts or [])))
        if (
            req.prompt is not None
            or req.image_urls
            or req.audio_urls
            or req.extra_user_content_parts
        ):
            messages.append(self._request_user_message_preview(req))
        if req.system_prompt:
            messages.insert(0, {"role": "system", "content": req.system_prompt})
        return messages

    def _request_user_message_preview(self, req: ProviderRequest) -> dict[str, Any]:
        content_blocks: list[dict[str, Any]] = []

        if req.prompt and req.prompt.strip():
            content_blocks.append({"type": "text", "text": req.prompt})
        elif req.image_urls:
            content_blocks.append({"type": "text", "text": "[图片]"})
        elif req.audio_urls:
            content_blocks.append({"type": "text", "text": "[音频]"})

        for part in req.extra_user_content_parts or []:
            content_blocks.append(self._jsonable(part))
        for image_url in req.image_urls or []:
            content_blocks.append(
                {"type": "image_url", "image_url": {"url": image_url}}
            )
        for audio_url in req.audio_urls or []:
            content_blocks.append(
                {"type": "audio_url", "audio_url": {"url": audio_url}}
            )

        if (
            len(content_blocks) == 1
            and content_blocks[0].get("type") == "text"
            and not req.extra_user_content_parts
            and not req.image_urls
            and not req.audio_urls
        ):
            return {"role": "user", "content": content_blocks[0]["text"]}
        return {"role": "user", "content": content_blocks}

    def _payload_log_filename(self, session_id: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_session = self._safe_filename(session_id)[:80] or "session"
        return f"{timestamp}_{safe_session}.json"

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "")).strip("._")

    def _cleanup_payload_logs(self) -> None:
        try:
            files = sorted(
                self._payload_log_dir.glob("*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for path in files[self._payload_log_max_files :]:
                path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to cleanup payload logs: {exc}")

    def _jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, list | tuple | set):
            return [self._jsonable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            try:
                return self._jsonable(value.model_dump())
            except Exception:  # noqa: BLE001
                return repr(value)
        if is_dataclass(value):
            try:
                return self._jsonable(asdict(value))
            except Exception:  # noqa: BLE001
                return repr(value)
        return repr(value)

    def _raw_config_text(self, key: str) -> str:
        raw = self.config.get(key, "")
        if raw is None:
            return ""
        return str(raw)

    def _nsfw_style_text(self) -> str:
        custom = str(self.config.get("nsfw_style_text", "") or "").strip()
        if custom:
            return custom
        try:
            raw = self._style_file.read_text(encoding="utf-8")
            return self._strip_frontmatter(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[nsfw_mode] failed to read built-in style: {exc}")
            return ""

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        lines = content.split("\n")
        if not lines or lines[0].strip() != "---":
            return content.strip()
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[index + 1 :]).strip()
        return content.strip()

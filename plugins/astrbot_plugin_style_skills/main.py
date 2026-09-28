"""astrbot_plugin_style_skills

自动发现插件内置 skills/ 与独立 style skills 目录下以特定前缀命名的
Skill 目录，把它们视为"风格"。
每个 session 有一个当前风格；每次 LLM 请求前把核心规则与当前风格的
SKILL.md 内容追加到 system_prompt 末尾，这样就不用再靠 LLM 自己用工具
调用去切换风格，节省一次乃至多次 tool 调用轮次。

与 AstrBot 原生 Skills progressive-disclosure 机制并存：那套机制是 LLM
按需 open_skill 按需展开；本插件则是"根据用户/命令选定的风格自动把对应
Skill 的正文一次性铺开到 system_prompt"，走的是另一条路。

命令：
  /style list           列出可用风格
  /style current        查看当前风格
  /style switch <name>  切换当前 session 的风格
  /style reload         重新扫描内置 skills 与独立 style skills 目录
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_style_skills",
    "Hartman",
    "为 persona 单角色场景自动注入核心规则与当前写作风格",
    "0.4.0",
    "",
)
class StyleSkillsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

        # Resolve the global AstrBot skills dir. It is only used when
        # scan_global_skills_dir is enabled; style injection defaults to the
        # isolated plugin data dir so normal skill discovery cannot see it.
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_skills_path

            self._global_skills_dir = Path(get_astrbot_skills_path())
        except Exception as e:
            logger.warning(f"[style_skills] 无法获取 skills 目录: {e}")
            self._global_skills_dir = Path("data/skills")
        self._builtin_skills_dir = Path(__file__).resolve().parent / "skills"

        # Persistent session → style map (lives under data/, not under plugin dir
        # per AstrBot 开发规范：persistent state 放 data/plugin_data/ 下)
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            data_root = Path(get_astrbot_data_path()) / "plugin_data" / "style_skills"
        except Exception:
            data_root = Path("data/plugin_data/style_skills")
        data_root.mkdir(parents=True, exist_ok=True)
        self._data_root = data_root
        self._isolated_skills_dir = self._resolve_style_skills_dir()
        self._isolated_skills_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = data_root / "session_styles.json"
        self._closed_file = data_root / "closed_sessions.json"
        self._session_styles: dict[str, str] = self._load_state()
        self._closed_sessions: set[str] = self._load_closed()

        # Cache of style_name → SKILL.md body
        self._cache: dict[str, str] = {}
        self._descriptions: dict[str, str] = {}
        self._kinds: dict[str, str] = {}
        self._skills_signature: dict[str, int] = {}
        self._load_skills()

    # ------------------------------------------------------------------
    # Config accessors (live, so WebUI edits take effect without reload)
    # ------------------------------------------------------------------

    @property
    def _enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    @property
    def _skill_prefix(self) -> str:
        return str(self.config.get("skill_prefix", "single-style-") or "single-style-")

    @property
    def _core_skill(self) -> str:
        return str(self.config.get("core_skill", "single-roleplay-core") or "").strip()

    @property
    def _default_style(self) -> str:
        return str(self.config.get("default_style", "daily") or "daily").strip()

    @property
    def _inject_header(self) -> str:
        return str(self.config.get("inject_header", "## 单角色扮演注入") or "")

    @property
    def _auto_reload(self) -> bool:
        return bool(self.config.get("auto_reload", True))

    @property
    def _scan_global_skills_dir(self) -> bool:
        return bool(self.config.get("scan_global_skills_dir", False))

    def _resolve_style_skills_dir(self) -> Path:
        raw = str(self.config.get("style_skills_dir", "") or "").strip()
        if not raw:
            return self._data_root / "injected_skills"
        path = Path(raw)
        if path.is_absolute():
            return path
        return self._data_root / path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, str]:
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if v}
        except Exception as e:
            logger.warning(f"[style_skills] 读取 session_styles 失败: {e}")
        return {}

    def _save_state(self) -> None:
        try:
            self._state_file.write_text(
                json.dumps(self._session_styles, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[style_skills] 保存 session_styles 失败: {e}")

    def _load_closed(self) -> set[str]:
        try:
            if self._closed_file.exists():
                data = json.loads(self._closed_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return {str(x) for x in data if x}
        except Exception as e:
            logger.warning(f"[style_skills] 读取 closed_sessions 失败: {e}")
        return set()

    def _save_closed(self) -> None:
        try:
            self._closed_file.write_text(
                json.dumps(sorted(self._closed_sessions), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[style_skills] 保存 closed_sessions 失败: {e}")

    def _is_closed(self, session_id: str) -> bool:
        return session_id in self._closed_sessions

    # ------------------------------------------------------------------
    # Skill discovery
    # ------------------------------------------------------------------

    def _load_skills(self) -> None:
        self._cache.clear()
        self._descriptions.clear()
        self._kinds.clear()

        self._isolated_skills_dir = self._resolve_style_skills_dir()
        self._isolated_skills_dir.mkdir(parents=True, exist_ok=True)

        if not self._isolated_skills_dir.exists():
            logger.warning(
                f"[style_skills] 隔离 style skills 目录不存在: {self._isolated_skills_dir}，"
                f"将仅尝试加载插件内置风格。"
            )

        skill_roots = self._skill_roots()
        if not skill_roots:
            logger.warning(
                f"[style_skills] 未找到可用的 skills 目录："
                f"{self._builtin_skills_dir}, {self._isolated_skills_dir}"
            )
            return

        prefix = self._skill_prefix
        if prefix:
            for root in skill_roots:
                kind = "isolated-style"
                if self._same_path(root, self._builtin_skills_dir):
                    kind = "builtin-style"
                elif self._same_path(root, self._global_skills_dir):
                    kind = "global-style"
                for child in sorted(root.iterdir()):
                    if not child.is_dir() or not child.name.startswith(prefix):
                        continue
                    style_name = child.name[len(prefix) :]
                    if style_name:
                        self._load_skill_dir(child, style_name, kind=kind)
        else:
            logger.warning("[style_skills] skill_prefix 为空，跳过前缀风格扫描")

        core_key = self._core_skill
        if core_key:
            core_dir = None
            for root in reversed(skill_roots):
                candidate = root / core_key
                if candidate.is_dir():
                    core_dir = candidate
                    break
            if core_dir and core_dir.is_dir():
                kind = "isolated-core"
                if self._same_path(core_dir.parent, self._builtin_skills_dir):
                    kind = "builtin-core"
                elif self._same_path(core_dir.parent, self._global_skills_dir):
                    kind = "global-core"
                self._load_skill_dir(core_dir, core_key, kind=kind)

        logger.info(
            f"[style_skills] 加载了 {len(self._cache)} 个 Skill: "
            f"{sorted(self._cache.keys())}"
        )

        if self.config.get("strict_warn_missing_default", True):
            dflt = self._resolve_style_name(self._default_style)
            if dflt and dflt not in self._cache:
                logger.warning(
                    f"[style_skills] 默认风格 '{dflt}' 未在 skills 目录中发现；"
                    f"未命名风格的 session 不会被注入任何内容。"
                    f"可用: {sorted(self._cache.keys())}"
                )
        self._skills_signature = self._build_skills_signature()

    def _skill_roots(self) -> list[Path]:
        roots: list[Path] = []
        seen: set[Path] = set()
        candidates = [self._builtin_skills_dir, self._isolated_skills_dir]
        if self._scan_global_skills_dir:
            candidates.append(self._global_skills_dir)
        for root in candidates:
            try:
                resolved = root.resolve()
            except Exception:
                resolved = root
            if root.exists() and root.is_dir() and resolved not in seen:
                roots.append(root)
                seen.add(resolved)
        return roots

    @staticmethod
    def _same_path(left: Path, right: Path) -> bool:
        try:
            return left.resolve() == right.resolve()
        except Exception:
            return left == right

    def _build_skills_signature(self) -> dict[str, int]:
        signature: dict[str, int] = {}
        prefix = self._skill_prefix
        core_key = self._core_skill
        for root in self._skill_roots():
            try:
                resolved_root = root.resolve()
                signature[f"root:{resolved_root}"] = root.stat().st_mtime_ns
            except Exception:
                continue
            try:
                children = sorted(root.iterdir())
            except Exception:
                continue
            for child in children:
                if not child.is_dir():
                    continue
                is_style = bool(prefix and child.name.startswith(prefix))
                is_core = bool(core_key and child.name == core_key)
                if not is_style and not is_core:
                    continue
                skill_file = child / "SKILL.md"
                try:
                    signature[str(skill_file.resolve())] = (
                        skill_file.stat().st_mtime_ns if skill_file.exists() else -1
                    )
                except Exception:
                    signature[str(skill_file)] = -1
        return signature

    def _reload_skills_if_changed(self) -> None:
        if not self._auto_reload:
            return
        current = self._build_skills_signature()
        if current != self._skills_signature:
            logger.info("[style_skills] 检测到 style skill 文件变化，自动重载")
            self._load_skills()

    def _load_skill_dir(
        self,
        child: Path,
        key: str,
        *,
        kind: str,
    ) -> None:
        skill_file = child / "SKILL.md"
        if not skill_file.exists():
            return
        try:
            raw = skill_file.read_text(encoding="utf-8")
            body = self._strip_frontmatter(raw)
            if not body:
                return
            self._cache[key] = body
            self._descriptions[key] = self._extract_description(raw)
            self._kinds[key] = kind
        except Exception as e:
            logger.warning(f"[style_skills] 读取 {skill_file} 失败: {e}")

    def _resolve_style_name(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        if name in self._cache:
            return name
        prefix = self._skill_prefix
        if prefix and name.startswith(prefix):
            trimmed = name[len(prefix) :]
            if trimmed in self._cache:
                return trimmed
        return name

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """剥掉 SKILL.md 头部的 YAML frontmatter（--- ... ---）"""
        lines = content.split("\n")
        if not lines or lines[0].strip() != "---":
            return content.strip()
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1 :]).strip()
        return content.strip()

    @staticmethod
    def _extract_description(content: str) -> str:
        m = re.search(r'^description:\s*["\']?(.*?)["\']?\s*$', content, re.MULTILINE)
        return m.group(1).strip() if m else ""

    # ------------------------------------------------------------------
    # Session style accessors
    # ------------------------------------------------------------------

    def _get_session_style(self, session_id: str) -> str:
        resolved = self._resolve_style_name(
            self._session_styles.get(session_id, self._default_style)
        )
        if resolved in self._cache:
            return resolved
        default_style = self._resolve_style_name(self._default_style)
        if default_style in self._cache:
            return default_style
        return resolved

    def _set_session_style(self, session_id: str, style: str) -> None:
        self._session_styles[session_id] = self._resolve_style_name(style)
        self._save_state()

    def _injection_status_lines(self, session_id: str) -> list[str]:
        current = self._get_session_style(session_id)
        core_key = self._resolve_style_name(self._core_skill)
        core_loaded = bool(core_key and self._cache.get(core_key))
        style_loaded = bool(current and current in self._cache and current != core_key)
        closed = self._is_closed(session_id)

        if not self._enabled:
            effective = "关闭（插件配置 enabled=false）"
        elif closed:
            effective = "关闭（本 session 已 /style close）"
        elif not self._cache:
            effective = "关闭（未加载到任何风格 Skill）"
        elif not core_loaded and not style_loaded:
            effective = "关闭（core 与当前风格均未加载）"
        else:
            effective = "开启"

        layers = []
        if core_loaded:
            layers.append(core_key)
        if style_loaded:
            layers.append(current)

        return [
            f"插件配置：{'启用' if self._enabled else '关闭'}",
            f"本 session 注入：{'关闭' if closed else '开启'}",
            f"实际注入状态：{effective}",
            f"核心规则：{core_key or '未配置'}"
            f"{' [已加载]' if core_loaded else ' [未加载]'}",
            f"当前写作风格：{current or '未配置'}"
            f"{' [已加载]' if style_loaded or current == core_key else ' [未加载]'}",
            f"注入层：{', '.join(layers) if layers else '无'}",
            f"隔离目录：{self._isolated_skills_dir}",
            f"兼容扫描 data/skills：{'开启' if self._scan_global_skills_dir else '关闭'}",
            f"实际扫描目录：{', '.join(str(path) for path in self._skill_roots()) or '无'}",
            f"自动热重载：{'开启' if self._auto_reload else '关闭'}",
        ]

    # ------------------------------------------------------------------
    # Hook: inject style into system_prompt
    # ------------------------------------------------------------------

    @filter.on_llm_request()
    async def on_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        if not self._enabled:
            return
        self._reload_skills_if_changed()
        if not self._cache:
            return  # no styles discovered, nothing to inject

        session_id = event.unified_msg_origin
        if self._is_closed(session_id):
            return  # session-level disabled
        style = self._get_session_style(session_id)

        sections: list[tuple[str, str]] = []
        layers: list[str] = []

        # 1) core skill if configured
        core_key = self._resolve_style_name(self._core_skill)
        if core_key:
            core_body = self._cache.get(core_key, "")
            if core_body:
                layers.append(core_key)
                sections.append(("全局单角色扮演核心规则", core_body))

        # 2) specific style body (skip if it IS the core to avoid duplication)
        if style and style != core_key:
            body = self._cache.get(style, "")
            if body:
                layers.append(style)
                sections.append((f"当前写作风格: {style}", body))

        if not sections:
            return

        block = "\n\n---\n\n".join(f"### {title}\n\n{body}" for title, body in sections)
        header = self._inject_header
        if header:
            suffix = f"\n\n{header} (当前: {style})\n{block}"
        else:
            suffix = f"\n\n{block}"

        req.system_prompt = (req.system_prompt or "").rstrip() + suffix
        event.set_extra("single_role_style_active", True)
        event.set_extra("single_role_style_name", style)
        event.set_extra("single_role_injection_layers", layers)
        event.set_extra(
            "single_role_style_guidance",
            self._review_guidance_excerpt(sections),
        )

    @staticmethod
    def _review_guidance_excerpt(sections: list[tuple[str, str]]) -> str:
        """Keep a compact style excerpt for downstream reviewers."""
        keywords = (
            "角色",
            "台词",
            "台词功能",
            "语气",
            "声线",
            "口癖",
            "助词",
            "日常",
            "亲密",
            "恋爱",
            "可爱",
            "喜欢",
            "温柔",
            "少女感",
            "少女",
            "主动",
            "靠近",
            "撒娇",
            "调侃",
            "软出口",
            "轻条件",
            "关系让步",
            "强势",
            "群像",
            "训话",
            "单向",
            "开放位",
            "重复提问",
            "重复触发",
            "再问",
            "媒介分工",
            "媒介目标",
            "后台计划",
            "写作意图",
            "字幕式旁白",
            "解释层",
            "话轮压迫",
            "话轮压力",
            "声线补丁",
            "可接",
            "未完成动作",
            "心理",
            "OOC",
            "禁止",
            "不要",
            "希儿",
        )
        chunks: list[str] = []
        for title, body in sections:
            selected: list[str] = []
            for raw_line in (body or "").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line == "---" or line.startswith(
                    ("name:", "description:", "license:", "metadata:")
                ):
                    continue
                if line.startswith("#") or any(word in line for word in keywords):
                    selected.append(line)
                if len("\n".join(selected)) >= 1500:
                    break
            if selected:
                chunks.append(f"【{title}】\n" + "\n".join(selected))
            if len("\n\n".join(chunks)) >= 2800:
                break
        return "\n\n".join(chunks)[:3200]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @filter.command_group("style")
    def style_group(self):
        """风格管理"""

    @style_group.command("help")
    async def style_help(self, event: AstrMessageEvent):
        """显示风格插件帮助"""
        lines = [
            "Style Skills 命令：",
            "  /style help - 显示本帮助",
            "  /style status - 查看插件开关、本 session 注入状态、core/style 是否加载",
            "  /style list - 列出可用写作风格",
            "  /style current - 查看当前写作风格",
            "  /style switch <name> - 切换写作风格，例如 daily / nsfw",
            "  /style reload - 重新扫描内置 skills 与隔离目录",
            "  /style close - 关闭本 session 的风格注入",
            "  /style open - 恢复本 session 的风格注入",
            "",
            "确认单角色模式：先执行 /style status，看到“实际注入状态：开启”且“注入层”包含 single-roleplay-core 与 daily/nsfw 即可。",
        ]
        yield event.plain_result("\n".join(lines))

    @style_group.command("list")
    async def style_list(self, event: AstrMessageEvent):
        """列出所有可用风格"""
        self._reload_skills_if_changed()
        if not self._cache:
            yield event.plain_result(
                f"没有发现任何风格 Skill。当前前缀 '{self._skill_prefix}' 下，"
                f"在 {self._isolated_skills_dir} 里没有找到匹配目录。"
            )
            return

        session_id = event.unified_msg_origin
        current = self._get_session_style(session_id)
        lines = ["可用风格："]
        for name in sorted(self._cache.keys()):
            desc = self._descriptions.get(name, "")
            if len(desc) > 80:
                desc = desc[:80] + "..."
            marker = " ★当前" if name == current else ""
            kind = self._kinds.get(name, "style")
            core_tag = (
                " (core)" if name == self._resolve_style_name(self._core_skill) else ""
            )
            kind_tag = f" [{kind}]"
            lines.append(f"  • {name}{core_tag}{kind_tag}{marker}  {desc}")
        if current not in self._cache:
            lines.append(f"\n⚠️ 当前风格 '{current}' 不在已发现列表里 → 不会注入内容")
        yield event.plain_result("\n".join(lines))

    @style_group.command("current")
    async def style_current(self, event: AstrMessageEvent):
        """查看当前 session 的风格"""
        self._reload_skills_if_changed()
        current = self._get_session_style(event.unified_msg_origin)
        ok = "" if current in self._cache else " (⚠️ 未发现对应 Skill，不会注入)"
        yield event.plain_result(f"当前写作风格：{current}{ok}")

    @style_group.command("status")
    async def style_status(self, event: AstrMessageEvent):
        """查看本 session 的注入状态"""
        self._reload_skills_if_changed()
        yield event.plain_result(
            "\n".join(self._injection_status_lines(event.unified_msg_origin))
        )

    @style_group.command("switch")
    async def style_switch(self, event: AstrMessageEvent, name: str = ""):
        """切换当前 session 的风格"""
        self._reload_skills_if_changed()
        name = (name or "").strip()
        if not name:
            yield event.plain_result("用法：/style switch <风格名>")
            return
        resolved = self._resolve_style_name(name)
        if resolved not in self._cache:
            available = ", ".join(sorted(self._cache.keys())) or "无"
            yield event.plain_result(
                f"未知风格 '{name}'。可用：{available}\n"
                f"（可以先用 /style reload 重新扫描 skills 目录）"
            )
            return
        self._set_session_style(event.unified_msg_origin, resolved)
        yield event.plain_result(f"已切换风格 → {resolved}")

    @style_group.command("reload")
    async def style_reload(self, event: AstrMessageEvent):
        """重新扫描 skills 目录"""
        self._load_skills()
        yield event.plain_result(
            f"已重新扫描，当前发现 {len(self._cache)} 个风格：{sorted(self._cache.keys())}"
        )

    @style_group.command("close")
    async def style_close(self, event: AstrMessageEvent):
        """关闭本 session 的风格注入（不影响其他 session）"""
        session_id = event.unified_msg_origin
        if session_id in self._closed_sessions:
            yield event.plain_result("本 session 的风格注入已经是关闭状态。")
            return
        self._closed_sessions.add(session_id)
        self._save_closed()
        yield event.plain_result(
            "已关闭本 session 的风格注入。/style open 可重新开启。\n"
            "（插件对其他 session 仍然生效；如要全局关闭请在 WebUI 的插件配置里改 enabled。）"
        )

    @style_group.command("open")
    async def style_open(self, event: AstrMessageEvent):
        """恢复本 session 的风格注入"""
        session_id = event.unified_msg_origin
        if session_id not in self._closed_sessions:
            yield event.plain_result("本 session 的风格注入已经是开启状态。")
            return
        self._closed_sessions.discard(session_id)
        self._save_closed()
        yield event.plain_result("已恢复本 session 的风格注入。")

# astrbot_plugin_style_skills

为非 RPG 的单角色 persona 场景自动注入“核心规则 + 当前写作风格”。

角色卡本体不由本插件扫描或注入。推荐用法是：玩家在 AstrBot persona 层创建角色 persona，例如“爱莉希雅”“格蕾修”“流萤”，把该角色 `SKILL.md` 内容写入 persona 的 system prompt，并限制 persona 只允许使用对应角色 Skill。`style_skills` 只负责在这个 persona 之上补充统一的文本质量、篇幅、标点、关系推进和写作风格约束。

## 工作原理

1. 启动时先扫描插件内置 `skills/`，再扫描独立 style skills 目录下所有以 `skill_prefix` 命名的风格目录。默认独立目录为 `data/plugin_data/style_skills/injected_skills`。
2. 默认 `skill_prefix=single-style-`，因此 `single-style-daily` 会注册为风格 `daily`，`single-style-nsfw` 会注册为风格 `nsfw`。
3. 每次 LLM 请求前，插件把 `core_skill` 和当前 session 的写作风格追加到 `req.system_prompt` 末尾。
4. 默认 `core_skill=single-roleplay-core`，用于给 persona 单角色扮演补上篇幅、文风、标点、默认场景、关系推进和出戏边界。
5. 默认风格是 `daily`，所以普通使用时实际注入为 `single-roleplay-core + single-style-daily`。

同名风格存在两份时，独立 style skills 目录会覆盖插件内置 `skills/`，方便本地调试和热修。默认不再扫描 `data/skills/`，避免这些风格被 AstrBot 原生 Skills 工具检索到。

## 命令

| 命令 | 说明 |
|------|------|
| `/style help` | 显示内置命令帮助 |
| `/style list` | 列出可用写作风格（标注当前） |
| `/style current` | 查看当前 session 的写作风格 |
| `/style status` | 查看插件开关、本 session 注入状态、core/style 是否加载 |
| `/style switch <name>` | 切换当前写作风格，例如 `daily` / `nsfw` |
| `/style reload` | 重新扫描 skills 目录 |
| `/style close` | 关闭本 session 的注入（不影响其他 session） |
| `/style open` | 恢复本 session 的注入 |

## 配置

- `enabled`：开关
- `skill_prefix`：风格目录名前缀，默认 `single-style-`
- `style_skills_dir`：独立 style skills 目录，默认 `data/plugin_data/style_skills/injected_skills`
- `auto_reload`：每次 LLM 请求前检测 `SKILL.md` 变化并自动重载，默认开启
- `scan_global_skills_dir`：兼容扫描全局 `data/skills`，默认关闭；开启后这些 style 仍会被原生 Skills 工具检索到
- `core_skill`：可选的核心 Skill 名，默认 `single-roleplay-core`
- `default_style`：新 session 未显式选过时使用的写作风格，默认 `daily`
- `inject_header`：注入段落的小标题
- `strict_warn_missing_default`：默认风格找不到对应 Skill 时打 WARN

## 推荐使用方式

1. 在 AstrBot persona 层创建角色 persona，并把角色 `SKILL.md` 放入 persona system prompt。
2. 切换到该 persona。
3. 保持默认风格 `daily`，或按需要切换：

```text
/style switch daily
/style switch nsfw
```

此时注入结构是：

```text
persona 角色卡
+ single-roleplay-core
+ single-style-daily 或 single-style-nsfw
```

## 和 RPG 插件同时使用？

RPG 插件有自己的 `rpg-style-*` 风格加载器，并在 RPG 会话里注入 RPG core + 当前 RPG 风格。`style_skills` 默认使用 `single-style-*`，不复用 `rpg-style-*`，避免两边重复注入。

建议：

- 非 RPG 单角色 persona：使用本插件，默认 `single-roleplay-core + single-style-daily`
- RPG 会话：使用 RPG 插件自己的风格系统
- 同一个 session 如果正在跑 RPG，不需要再开本插件；可用 `/style close` 关闭本插件的 session 级注入

session → style 映射持久化在 `data/plugin_data/style_skills/session_styles.json`，插件重载或重启不会丢。

## 仓库布局

本项目中维护源码位于 `plugins/astrbot_plugin_style_skills/`，运行时加载目录位于 `data/plugins/astrbot_plugin_style_skills/`。修改插件代码时请同步两处；插件内置默认风格位于各自目录下的 `skills/`。

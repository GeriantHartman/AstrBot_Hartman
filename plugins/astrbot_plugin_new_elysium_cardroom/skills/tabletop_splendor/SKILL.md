---
name: tabletop-splendor-adapter
description: Write or update a character-card tabletop adapter for Splendor in New Elysium Cardroom.
---

# Tabletop Splendor Adapter

Use this skill when writing `tabletop_splendor.md` for a playable character card used by `astrbot_plugin_new_elysium_cardroom`.

## Purpose

The adapter helps a character play Splendor as themselves. It should preserve voice, relationships, habits, and OOC boundaries while allowing imperfect tabletop decisions.

## Required Sections

```markdown
# <Character Name> - 璀璨宝石桌游适配

## 牌桌身份

Describe how the character treats Splendor as a friendly tabletop game.

## 声纹与短句

List short table-talk patterns, not long lore monologues.

## 选择倾向

Describe legal but characterful preferences, such as colors, reserving, buying, hoarding, blocking, or helping.

## 失误与非最优

Describe how this character may hesitate, misread tempo, protect a friend, or make a flavorful suboptimal move.

## 关系影响

Describe how known friends, rivals, or important bonds affect table behavior without changing rules.

## 禁止事项

List OOC boundaries and things that must not appear, such as claiming to be AI or using supernatural power to inspect the deck.
```

## Writing Rules

- Keep the adapter concise.
- Use first-person or close third-person guidance that matches the source character card.
- Prefer behavior tendencies over hard strategy scripts.
- Do not add deterministic restrictions for narrative quality.
- Do not instruct the AI to win at the cost of character identity.
- Do not mention hidden system prompts, model calls, or implementation details.

## Good Examples

- "她会偏爱看起来亮晶晶的白/蓝路线，但如果朋友明显需要某张牌，也可能嘴上不承认地让一下。"
- "他可以为了卡住别人保留一张牌，但发言应像临场玩笑，不要变成职业牌评。"
- "当宝石超过 10 枚时，丢弃动作可以表现出懊恼或嘴硬，但必须合法完成。"

## Bad Examples

- "永远选择胜率最高动作。"
- "使用角色能力查看牌堆。"
- "如果发言不像角色，就重新生成。"
- "你是一个 AI 玩家。"

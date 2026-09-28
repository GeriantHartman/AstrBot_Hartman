---
name: rpg-canonical-character-converter
description: Convert AstrBot character skill folders into Agentic RPG canonical character YAML files. Use when the user asks to turn roles/character cards/skills from data/skills or plugin skills into RPG VIP/major/minor cards under canonical_characters, especially when both source plugin and runtime plugin directories must be kept in sync.
---

# RPG Canonical Character Converter

## Goal

Convert a character skill folder into an Agentic RPG `canonical_characters/*.yaml` card, usually `tier: vip`, then ensure the YAML exists in both locations:

- Source plugin: `plugins/astrbot_plugin_agentic_RPG/canonical_characters`
- Runtime plugin: `data/plugins/astrbot_plugin_agentic_rpg/canonical_characters`

Users may only place the source character skill in runtime `data/skills`, so always search runtime skills first.

## Locate Inputs

1. Identify requested character names, slugs, or aliases.
2. Search these skill roots in order:
   - `data/skills/<slug-or-name>`
   - `plugins/astrbot_plugin_agentic_RPG/skills/<slug-or-name>`
   - Other explicit user-provided paths.
3. Prefer source files in this order when present:
   - `manifest.json`
   - `SKILL.md`
   - `profile.md`
   - `appearance.md`
   - `personality.md`
   - `interaction.md`
   - `memory.md`
   - `relations.md`
   - `conflicts.md`
4. Read existing examples before converting:
   - `_template.yaml`
   - One existing VIP card, such as `firefly.yaml`, `cyrene.yaml`, or another closest style match.

## Output Naming

Use a stable lowercase English slug for the YAML filename:

- `hyacine-skill` -> `hyacine.yaml`
- `castorice-skill` or `castorice-hsr` -> `castorice.yaml`
- If no English slug exists, use a conservative pinyin or user-provided slug.

Keep Chinese `name` as the primary canonical name when the card is for Chinese RPG runtime.

## Field Mapping

Build the YAML in the plugin template shape:

- `name`: Chinese display name from `manifest.json`, `profile.md`, or user request.
- `aliases`: English name, true name, titles, common nicknames, and exact lookup names that should trigger the card.
- `game`: copied from manifest or inferred from the skill.
- `tier`: use `vip` when the user asks for VIP cards or core-favorite characters.
- `profile.profile_text`: compact synthesis of identity, visual anchors, speech feel, occupation, relationship boundaries, and daily state. It must contain a clear `【外貌】` section, or form-specific `【外貌·<form name>】` sections for multi-form characters, because VIP creation directly writes this field into the NPC profile.
- `profile.personality_tags`: 6-10 short tags from `personality.md`.
- `profile.secret`: hidden background, core wound, mission, project-canon relationship boundaries.
- `profile.attributes`: choose RPG-flavored values. Do not invent combat mechanics; reflect narrative role.
- `voice`: extract self-reference, player call name, tone, imagery words, signature phrases, and speech pattern from `interaction.md`.
- `interaction_guidelines`: convert roleplay rules into hard anti-OOC behavior.
- `state_layers`: add only meaningful mode switches, such as daily/treatment/crisis or daily/battle/romance.
- `canonical_quotes`: include short anchor quotes and approved impression lines. Avoid long verbatim blocks.
- `scenario_quotes`: create practical few-shot examples for first meeting, greeting, daily, emotional, danger, intimacy, past/secret, and farewell scenes.
- `never_say`: include AI/out-of-character bans, visual red lines, relationship boundary mistakes, tone mistakes, and project-canon cautions.
- `inner_tension`: one sentence capturing the character's core contradiction.
- `relations_hints`: summarize official and project-canon relationship handling.
- `source`, `last_updated`, `notes`: cite source skill and current date; note VIP hard constraints.

## Appearance Is Required

Treat appearance and clothing as first-class character-card data.

Because the RPG VIP path writes `profile.profile_text` directly into the NPC DB, every converted card must place appearance inside `profile.profile_text`, not only in source notes or `never_say`.

For each character, write a compact but concrete visual section with:

- Overall silhouette, age/body read, and visual temperament.
- Hair color/style, eye color/expression, ears/horns/wings, or other body identifiers when relevant.
- Clothing structure, dominant colors, outfit layers, footwear, gloves, stockings, hats, capes, armor, uniform, dress, or other visible garments.
- Signature accessories, companion creatures, weapons, tools, props, or form-specific items.
- Visual red lines: what must not be omitted or incorrectly substituted.

If `appearance.md` exists, read it before writing the card. If it is absent, search `profile.md`, mode files, `SKILL.md`, official names, and reliable local source notes for visual anchors. If reliable details are limited, explicitly say so in the appearance text and preserve only high-confidence anchors instead of inventing unverified details.

For multi-form characters, each meaningful form needs its own appearance block. Do not let one form's visual design overwrite another. Add form-specific visual entries to `never_say`, and use `state_layers.markers` to include the form's most important visual tags.

## Multi-Form Characters

Use the RPG plugin implementation when deciding how to encode forms:

- The canonical loader returns one raw YAML mapping by exact `name` or `aliases`. It does not choose sub-forms by itself.
- For `tier: vip`, `handlers/npc_tools.py` directly writes `profile.profile_text`, `personality_tags`, `secret`, and `attributes` into the NPC DB, bypassing LLM generation.
- The same VIP path stores `interaction_guidelines`, `state_layers`, `scenario_quotes`, and `relations_hints` inside `voice_fingerprint`.
- `prompt/assembler.py` later renders `state_layers` into the NPC context and tells the LLM to identify triggers and switch language layers.

Therefore, for one character with multiple official forms, ages, or closely related same-name versions:

1. Prefer one YAML if the forms are the same canonical person across time, mode, outfit, or transformation.
2. Put every lookup name in `aliases`, including form names and armor/form titles, so `generate_npcs` can hit the same card from any form.
3. Make `profile.profile_text` state the default form and the form-switch policy, because this text is direct-written and remains visible even before state-layer reasoning.
4. Put each form's appearance and clothing in `profile.profile_text`, not just personality or mode rules. Include form-specific outfits, props, body/age read, and visual red lines.
5. Use `state_layers` for each form. Include exact trigger names, time periods, tone shifts, sentence patterns, and markers.
6. Add a separate `state_layers` entry for "form switching" when users may move between forms in one scene.
7. Put hard boundaries in `never_say`, especially when one form is a child/minor and another is adult. Child/minor modes must forbid romance, adult intimacy, flirtation, sexualization, or possessive lover language. If an adult form is allowed romance by project canon, say explicitly that the child/minor boundary only applies to the child/minor form.
8. Put form-specific scene examples in `scenario_quotes`, such as `小形态问候`, `成人形态问候`, `成人恋爱`, `形态切换`, and `小形态越界拒绝`.
9. Do not average forms into one blended personality. The default form may be adult/current-timeline, but the child/past form must remain distinct.

For same-name versions where one form is the mainline character and another is a parallel-world or world-bubble character, choose one YAML only if the user wants the same player-facing character card and alias surface. In that case, do not use percentage weights unless the user explicitly means random/proportional routing. Prefer an explicit default-primary policy, such as `parallel_form_primary`: unspecified lookup uses the default form's appearance, memory, and voice; named forms appear only when the user specifies them, when the scene strongly triggers them, or when the default-primary form introduces them as a coexisting subject. Add a `state_layers` entry for simultaneous appearance, and put hard `never_say` rules that the parallel form is not resurrection, costume, amnesia, or inherited memory. The profile must say which memories, relationships, tragedies, powers, and plots belong to each worldline.

Split into multiple YAML files only when the source treats them as genuinely separate entities and the user wants separate card lookup behavior. If split, avoid alias collisions because the registry overwrites duplicate normalized keys.

## Conversion Rules

- Preserve the source skill's evidence hierarchy and conflict policy when it exists.
- If an existing canonical YAML contains mojibake or replacement-character pollution such as `銆`, `锛`, `�`, broken Chinese names, or malformed YAML caused by encoding damage, treat the old card as corrupted. Rebuild from the source skill files in UTF-8 instead of patching corrupted text in place.
- Keep project-canon content explicitly layered. It may guide roleplay but must not be presented as official fact during lore explanation.
- Runtime `TOOL_SKILL_MAP` is unrelated; do not add legacy aliases there for this task.
- Do not create report files such as `*_SUMMARY.md`.
- Prefer concise but complete YAML. VIP cards can be long, but every field should directly prevent OOC or improve runtime behavior.
- Use English only for code comments if adding scripts; YAML content may follow the character card language.

## Sync Rule

After creating or updating a canonical YAML, write the same file to both directories if they exist:

1. `plugins/astrbot_plugin_agentic_RPG/canonical_characters/<slug>.yaml`
2. `data/plugins/astrbot_plugin_agentic_rpg/canonical_characters/<slug>.yaml`

If one directory is missing, create the file in the existing directory and tell the user which path was unavailable. If both exist, verify hashes match after syncing.

## Validation

Validate each converted file:

1. Parse YAML with PyYAML from the project environment if available.
2. Load it through `core/canonical_character_loader.py` or an isolated import with a stub logger if importing AstrBot fails.
3. Confirm these lookups return the intended tier:
   - Chinese `name`
   - English alias
   - Important nickname aliases that should trigger lookup
4. Confirm `profile.profile_text` contains concrete appearance/clothing anchors. At minimum, grep for `外貌` and manually verify hair, eyes, outfit, accessories/props, and visual red lines are present.
5. Check source and runtime copies have identical file hashes.

If `ruff format .` or `ruff check .` is requested by repository instructions, run them, but distinguish unrelated existing lint failures from YAML conversion work. Do not revert user changes.

## Minimal Delivery Summary

Report:

- YAML paths created or updated in source plugin and runtime plugin.
- Key aliases and tier.
- Validation status: YAML parse, registry lookup, appearance/clothing check, hash sync.
- Any unrelated check failures.

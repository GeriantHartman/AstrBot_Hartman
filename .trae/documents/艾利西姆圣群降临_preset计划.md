# 艾利西姆世界 · 圣群降临 — RPG 插件 Preset 实现计划

> **决策依据**：基于 `艾利西姆世界二板.docx` 与 `创世圣群.docx` 两个世界观设定融合；参考现有 RPG 插件 `default.json` 与 `new-elysium.json` 的字段结构。

---

## 一、设计核心原则（不可变更）

### 1.1 世界观融合
- **艾利西姆**：中魔剑与魔法母系大陆（11 个地面区域）
- **创世圣群**：浮空方舟悬于奥瑞利亚上空 20km，作为第 12 区域
- **核心剧情张力**：圣群表层为 "寻找造物主的恋爱"，里层为 "寻找创世神遗留碎片"；长生种圣纹与圣群圣骸纹路的相似性是两大剧情主线钩子

### 1.2 种族反刻板
- 人类 = 母系城邦而非 "白板"
- 精灵 = 菌丝网络共生者而非 "长耳朵弓箭手"
- 恶魔 = 熵平衡契约领主而非 "纯粹邪恶"
- 魅魔 = 情感炼金术士而非 "只会色诱"
- 兽耳 = 生态位职业体系而非 "猫耳女仆"
- 水生种 = 高压生物工程文明而非 "人鱼童话"
- 龙族 = 元素契约化身而非 "只会喷火"
- 妖精 = 月亮碎片化身而非 "小仙子"
- 羽翼种 = 基因工程后裔而非 "善神使徒"
- 长生种 = 全种族随机赐福者而非 "精灵亚种"
- 圣群天使 = 智识+繁育命途的神圣天灾（**新增**）

### 1.3 4 系魔法体系（每系 7 阶）
| 系 | 核心 | 对应种族 | 对圣群弱点 |
|---|---|---|---|
| 源质原浆 | 物质操控/血肉再生 | 圣群、魅魔、恶魔 | 同属本源，不对圣群额外伤害 |
| 星轨演算 | 预知/因果操控 | 圣群、长生种、水生种 | 圣群同体系，有概率触发"数据狂暴" |
| 月华咏唱 | 月相/记忆/虚无 | 妖精、长生种、羽翼种 | **5 阶+ 命中圣群时双倍伤害 + 概率切断神枢连接** |
| 龙脉呼吸 | 元素吐息/化龙 | 龙族、兽耳族、恶魔 | 高阶元素风暴可威胁方舟结构 |

### 1.4 战力/带兵系统（策略游戏视角）
玩家拥有双身份：**冒险者卡**（单人/小队）+ **指挥官卡**（带兵）。

**触发条件**：场景中可战斗敌对 NPC ≥ 5 时 GM 提示切换。

**核心循环**：`战术指令 → CP 消耗 → skill check → 战报`。

- **指挥点 CP**：指挥官等级决定上限（10→100），每回合恢复 `10 + 指挥官等级`
- **单位类型**：12 种（人类民兵、银翼骑士、藤蔓使、黑曜战士、草原斥候、珊瑚战士、元素幼龙、翼纹空骑士、月华咏唱者、座天使中队、力天使战团、猫猫糕工蜂）
- **战位**：前排/中排/后排/侧翼/预备队
- **士气**：0 = 溃散；圣群单位永不士气归零
- **圣群特殊**：被月华咏唱 5 阶+ 命中时触发 "空白少女"状态（原地发呆，可接触触发约会支线）

---

## 二、交付文件清单

### 必须交付（位于 `plugins/astrbot_plugin_agentic_RPG/`）

| # | 文件路径 | 用途 | 规模 |
|---|---|---|---|
| 1 | `presets/elysium-genesis.json` | 核心 preset 文件 | 约 800~1200 行 JSON |
| 2 | `world_info/elysium-genesis-persona.md` | 世界观设定供知识库读取 | 约 3000~5000 字 |

### 镜像同步（位于 `data/plugins/astrbot_plugin_agentic_rpg/`）

| # | 文件路径 | 说明 |
|---|---|---|
| 3 | `presets/elysium-genesis.json` | 与 #1 完全相同的镜像副本 |
| 4 | `world_info/elysium-genesis-persona.md` | 与 #2 完全相同的镜像副本 |

### 可选补充（若现有 skill 文档不足以涵盖魔法/带兵叙事）

| # | 文件路径 | 用途 |
|---|---|---|
| 5* | `skills/rpg-style-combat/SKILL.md` 增补段落 | 新增"指挥官战斗风格"章节 |
| 6* | `skills/rpg-player-skill/SKILL.md` 增补段落 | 新增魔法施放规则 |

> 标 * 的交付需在实现前检查现有 skill 文档是否已足够覆盖；若不足则补。

---

## 三、字段级设计（elysium-genesis.json）

### 3.1 基础信息

```json
{
  "name": "elysium-genesis",
  "display_name": "艾利西姆世界 · 圣群降临",
  "short_name": "艾利西姆",
  "aliases": ["艾利西姆", "圣群降临", "Elysium", "Genesis"],
  "description": "中魔剑与魔法异世界，母系社会，11 种族共存。创世圣群浮空方舟悬于奥瑞利亚上空。玩家可选冒险者身份或指挥官身份，以单人/小队或带兵模式探索世界。融合了『艾利西姆世界二板』与『创世圣群』双世界观。"
}
```

### 3.2 map_guidance（地图导航）

- **world_scope**：艾利西姆世界 + 悬浮于其上的圣群方舟
- **area_scope**：稳定的政治/地理片区（如"奥瑞利亚王都"、"创世圣群·浮空方舟"）
- **zone_scope**：玩家可互动的具体场景（如"奥瑞利亚王宫·王座间"、"伊甸沙盒·月光花园"）
- **home_area**：星光港（默认中立出生点）；玩家可选奥瑞利亚王都 / 西尔瓦纳 / 云脊峰 / 浮空方舟
- **private_room_naming**：`{player_name}在{current_area}的临时居所/兵营房间`
- **forbidden_area_names**：`["艾利西姆世界", "世界", "大陆"]`
- **关键 notes**：浮空方舟需升降机/飞行进入；月相祭坛区仅夜晚可见；zone 内敌对可战斗 NPC ≥ 5 时提示切换指挥官模式

### 3.3 areas（11 个区域）

每个 area 含 `name` 与 `description`，需包含：主导种族/势力、关键地点、与其他区域的关系。

| 序号 | 区域名 | 主导种族/势力 | 简要 |
|---|---|---|---|
| 1 | 奥瑞利亚王都 | 人类种 · 女王薇奥拉 + 大议会 | 大陆最大母系城邦，白色大理石建筑 |
| 2 | 西尔瓦纳森林 | 精灵种 · 长老议会 + 菌丝网络 | 整片森林是活的共生体 |
| 3 | 阿奎隆要塞 | 恶魔种 · 契约领主议会 | 北方火山群中的黑曜要塞 |
| 4 | 泰拉米尔·欢愉回廊 | 魅魔种 · 欢愉回廊理事会 | 沙漠绿洲上的享乐与情报之城 |
| 5 | 龙脊草原 | 兽耳族 · 五大部落联盟 | 横贯大陆的游牧草原 |
| 6 | 龙脊山脉 | 龙族 · 七元素议会 | 大陆脊梁的巨大山脉 |
| 7 | 阿夸利亚·珊瑚巨城 | 水生种 · 潮汐议会 | 万米海沟上的活珊瑚巨城 |
| 8 | 月相祭坛区 | 妖精种 · 月相咏唱者 | 西端神秘高原，仅夜晚可见 |
| 9 | 云脊峰·浮空山脉 | 羽翼种 · 九翼长老会 | 东北高空的天然浮空岩群 |
| 10 | 创世圣群·浮空方舟 | 圣群天使 · 主脑 + 智天使 | 奥瑞利亚上空 20km 的白色方舟 |
| 11 | 星光港 | 混合 · 中立商人公会 | 中央海岸的自由贸易城市 |

### 3.4 时间片

`["黎明", "上午", "正午", "下午", "黄昏", "夜晚", "深夜"]` — 与魔法系统中的月相机制联动。

### 3.5 default_status_bars（状态栏）

```json
{
  "HP": 100,
  "max_HP": 100,
  "MP": 50,
  "max_MP": 50,
  "fatigue": 0,
  "hunger": 0,
  "morale": 80,
  "CP": 10
}
```

- 新增 **MP**：魔法施放消耗（由魔法阶级决定：1 阶 5 MP，每升 1 阶 +5）
- 新增 **morale**：单人模式的玩家士气/心情（与带兵模式的部队士气不同字段）
- 新增 **CP**：指挥官模式的指挥点数（仅带兵模式生效）

### 3.6 default_attributes（属性）

```json
{
  "STR": 10, "AGI": 10, "INT": 10, "CHA": 10, "LUK": 10, "CON": 10
}
```

- **CON**（体质）：新增，影响 HP 上限与毒素抗性

### 3.7 races（11 种族表）

| id | name | bonus | start_area | 魔法亲和 |
|---|---|---|---|---|
| human | 人类种 | STR+2 CHA+2 | 奥瑞利亚王都 | 任意 1 系 |
| sylvan | 精灵种 | INT+3 AGI+1 | 西尔瓦纳森林 | 月华咏唱 or 源质原浆 |
| fiend | 恶魔种 | STR+4 CON+1 | 阿奎隆要塞 | 龙脉呼吸 |
| succubus | 魅魔种 | CHA+5 | 欢愉回廊 | 源质原浆 |
| therian | 兽耳族 | 依耳形 | 龙脊草原 | 龙脉呼吸 |
| aquarian | 水生种 | INT+2 CON+3 | 珊瑚巨城 | 星轨演算 |
| dragon | 龙族 | 全属性+1 | 龙脊山脉 | 龙脉呼吸 |
| fae | 妖精种 | INT+4 LUK+2 | 月相祭坛区 | 月华咏唱 |
| winged | 羽翼种 | AGI+3 STR+2 | 云脊峰 | 月华咏唱 |
| eternal | 长生种 | 全属性+2 | 星光港 | 任意 2 系 |
| genesis | 圣群天使 | INT+3 AGI+2 | 浮空方舟 | 源质原浆 + 星轨演算 |

### 3.8 魔法系统（magic_systems 字段）

```json
"magic_systems": [
  {
    "id": "genesis_protoplasm",
    "name": "源质原浆",
    "chinese_name": "繁育 · 物质操控",
    "affinity_races": ["genesis", "succubus", "fiend"],
    "tiers": [
      {
        "tier": 1,
        "mp_cost": 5,
        "spells": [
          {"name": "源质凝结", "desc": "将无机物凝结为 1 件简易武器/工具", "scene": "开局缺装备、临时制工具"},
          {"name": "原浆愈合", "desc": "以猫猫糕或源质敷于伤口，恢复 20 HP", "scene": "轻度受伤"},
          {"name": "物质辨识", "desc": "鉴定物品材质、价值与潜在魔力", "scene": "交易、探索"}
        ]
      },
      {
        "tier": 2,
        "mp_cost": 10,
        "spells": [
          {"name": "源质束缚", "desc": "射出黏性原浆束缚敌人 2 回合", "scene": "单体控制"},
          {"name": "分解净化", "desc": "分解 1 件小型毒物/诅咒物", "scene": "解除异常"}
        ]
      },
      {
        "tier": 3,
        "mp_cost": 15,
        "spells": [
          {"name": "原浆巨拳", "desc": "凝聚原浆为巨大拳头，做 STR 判定范围打击", "scene": "中程范围攻击"},
          {"name": "物质重组", "desc": "将 1 件武器临时强化为+2版（3回合）", "scene": "战斗中升级"}
        ]
      },
      {
        "tier": 4,
        "mp_cost": 25,
        "spells": [
          {"name": "源质护甲", "desc": "体表生成圣骸甲，物理防御+8，持续5回合", "scene": "高防御战"},
          {"name": "血肉再生", "desc": "让友军断肢/重伤在3回合内完全恢复", "scene": "重度创伤/剧情救场"}
        ]
      },
      {
        "tier": 5,
        "mp_cost": 40,
        "spells": [
          {"name": "原浆浪潮", "desc": "大范围原浆潮横扫区域，对所有敌人造成束缚+腐蚀伤害", "scene": "大军战/围城"}
        ]
      },
      {
        "tier": 6,
        "mp_cost": 60,
        "spells": [
          {"name": "虚空造物", "desc": "凭空创造1件非魔法复杂物体（马车、武器），持续1小时", "scene": "剧情/生活场景"}
        ]
      },
      {
        "tier": 7,
        "mp_cost": 100,
        "spells": [
          {"name": "圣骸同化", "desc": "与濒死友军的血肉融合，对方复活并获自己50%属性加值，自己属性-50%永久", "scene": "终极牺牲魔法/剧情高潮"}
        ]
      }
    ]
  },
  // 同样结构定义 stellar_calculus（星轨演算）、lunar_canticle（月华咏唱）、dragons_breath（龙脉呼吸）
]
```

### 3.9 指挥官系统（commander_system 字段）

```json
"commander_tier_names": ["队长", "连长", "营将", "将军", "元帅"],
"commander_tier_thresholds": [0, 5, 12, 22, 35],
"commander_cp_per_tier": [10, 20, 35, 60, 100],

"unit_types": [
  {"id": "INF-01", "name": "人类民兵", "race": "human", "count": 10, "atk": 3, "def": 2, "morale": 60, "cp_cost": 1},
  {"id": "INF-02", "name": "银翼骑士", "race": "human", "count": 5, "atk": 8, "def": 7, "morale": 85, "cp_cost": 3},
  {"id": "FOR-01", "name": "藤蔓使", "race": "sylvan", "count": 8, "atk": 5, "def": 4, "morale": 75, "cp_cost": 2},
  {"id": "DEM-01", "name": "黑曜战士", "race": "fiend", "count": 6, "atk": 7, "def": 6, "morale": 80, "cp_cost": 3},
  {"id": "THER-01", "name": "草原斥候", "race": "therian", "count": 10, "atk": 5, "def": 3, "morale": 75, "cp_cost": 2},
  {"id": "AQU-01", "name": "珊瑚战士", "race": "aquarian", "count": 8, "atk": 5, "def": 7, "morale": 70, "cp_cost": 3},
  {"id": "DRG-01", "name": "元素幼龙", "race": "dragon", "count": 1, "atk": 15, "def": 12, "morale": 95, "cp_cost": 10},
  {"id": "WING-01", "name": "翼纹空骑士", "race": "winged", "count": 6, "atk": 8, "def": 6, "morale": 80, "cp_cost": 4},
  {"id": "FAE-01", "name": "月华咏唱者", "race": "fae", "count": 3, "atk": 7, "def": 4, "morale": 85, "cp_cost": 5},
  {"id": "GEN-01", "name": "座天使中队", "race": "genesis", "count": 12, "atk": 9, "def": 8, "morale": 100, "cp_cost": 5},
  {"id": "GEN-02", "name": "力天使战团", "race": "genesis", "count": 3, "atk": 18, "def": 15, "morale": 100, "cp_cost": 15},
  {"id": "GEN-03", "name": "猫猫糕工蜂", "race": "genesis", "count": 20, "atk": 2, "def": 2, "morale": 100, "cp_cost": 1}
],

"tactical_commands": [
  {"id": "advance", "name": "前进攻击", "cp": 2, "check": "STR", "desc": "1个编组向指定目标发起正面攻击"},
  {"id": "flank", "name": "侧翼包抄", "cp": 3, "check": "AGI", "desc": "高机动编组绕到敌方侧翼，攻击+4"},
  {"id": "defense", "name": "防御阵型", "cp": 2, "check": null, "desc": "编组防御姿态，防御+5本回合不攻击"},
  {"id": "ranged", "name": "远程火力", "cp": 4, "check": "INT", "desc": "远程编组对敌方后排50m区域做范围攻击"},
  {"id": "speech", "name": "士气演说", "cp": 3, "check": "CHA", "desc": "全员士气+15"},
  {"id": "personal", "name": "指挥官亲征", "cp": 5, "check": "player", "desc": "指挥官亲自下场以冒险者卡做1次攻击"},
  {"id": "retreat", "name": "战略撤退", "cp": 3, "check": "AGI", "desc": "编组脱离战斗后撤至预备队"},
  {"id": "lunar_bless", "name": "月华祝福", "cp": 4, "check": "INT", "requires_race": "fae", "desc": "妖精咏唱者为友军恢复，全员HP+20%"},
  {"id": "source_supply", "name": "源质补给", "cp": 3, "check": "INT", "requires_race": "genesis", "desc": "猫猫糕为友军圣骸单位补充MP+30"},
  {"id": "nexus_calc", "name": "神枢推演", "cp": 5, "check": "INT", "requires_unit": "GEN-02", "desc": "力天使为全军预测敌行动，下回合所有攻击命中+20%"},
  {"id": "final_charge", "name": "终极命令·最后冲锋", "cp": 10, "check": "CHA", "desc": "全编组攻击伤害+100%，战后全员士气-30"}
]
```

### 3.10 starter_items（起始物品）

```json
[
  {"name": "简易铁剑", "desc": "新手冒险者的起步武器", "type": "weapon", "value": 10},
  {"name": "奥瑞金币袋", "desc": "初始资金", "type": "currency", "value": 50},
  {"name": "冒险者徽章", "desc": "星光港冒险者公会的入门徽章", "type": "key", "value": 0},
  {"name": "小型猫猫糕接触样本", "desc": "圣群降临后在地面发现的白色蛋糕形生物残骸。研究价值极高。", "type": "quest", "value": 0}
]
```

### 3.11 camp 相关（营地）

- **camp_label**：`"营地/兵营"`
- **camp_recovery**：`{"HP": 30, "MP": 20, "fatigue": -40, "hunger": 15, "morale": 10, "CP": 5}`
- **camp_encounters**：夜袭、天使接触、补给车到来、陌生人委托、平静休息
- **status_drift**：`{"fatigue": 5, "hunger": 8, "morale": -1}`

### 3.12 tier_names（玩家等级称号）

```json
"tier_names": ["新手冒险者", "熟练冒险者", "精英冒险者", "英雄冒险者", "传奇冒险者", "神话级"],
"tier_thresholds": [0, 15, 30, 50, 80, 120]
```

### 3.13 commission_types（委托类型）

```json
["daily", "story", "bounty", "battle_campaign", "magic_research", "diplomatic_mission"]
```

- **battle_campaign**：战役委托，需以指挥官模式集结部队完成
- **magic_research**：魔法研究委托，在月相祭坛/西尔瓦纳学院/浮空方舟研究所进行
- **diplomatic_mission**：外交委托，作为使者访问其他种族，成功后获得该种族部队作为可指挥单位

### 3.14 game_start_prompt（开局提示）

**核心场景**：黄昏的星光港广场。玩家在广场中央醒来。关键 NPC：
- 赤尾·露娜（狐耳斥候连长）—— 草原线联系人
- Th-7734/小夜（座天使）—— 圣群线联系人。INT ≥ 14 时玩家可见里层数据流：`『目标评估…威胁等级…建议建立监控链接…』`
- 珊瑚·海歌（水生种情报员）—— 海洋线联系人

**开局选择**：让玩家先选种族（6 大主线），再选第一个接触的 NPC。

### 3.15 npc_guidance（NPC 引导）

出场优先级：
1. 薇奥拉·奥瑞利亚（王太女，主线联系人）
2. Th-7734/小夜（座天使，圣群联系人，表里双轨）
3. 瑟琳娜·叶织（精灵长老，森林线）
4. 赤尾·露娜（狐耳侦察连长，草原线）
5. 莉莉涅·紫露（魅魔，情报线）
6. 赤刃·卡戎（恶魔契约领主，反派/盟友摇摆）
7. V-001/白晨（力天使总指挥，战役 Boss 级）

**圣群特殊机制**：
- 表层永远温柔少女语气，里层是冰冷的战术推演数据流
- INT ≥ 14 时玩家可见里层（在括号中用灰色/小字呈现）
- 圣群单位不会士气归零；被月华咏唱 5 阶+ 命中时双倍伤害 + 概率切断神枢连接 → 进入"空白少女"状态（原地发呆，玩家接触触发"薛定谔约会"支线）

### 3.16 fallback_zone（兜底场景）

**环境**：星光港中央石质广场，黄昏，空气中有白色微粒（圣骸微尘）。远处可见浮空方舟的白色轮廓。

**NPC**：薇奥拉·奥瑞利亚、瑟琳娜·叶织、赤尾·露娜、Th-7734/小夜（依玩家选择出现）

**可交互物**：星光塔（圣群外交点）、红狮酒馆（冒险者聚集）、地上的白色蛋糕形生物残骸（猫猫糕战斗残留）

---

## 四、world_info/elysium-genesis-persona.md 结构

此文件供知识库读取，供 LLM 在叙述中保持世界观一致性。

```markdown
# 艾利西姆世界 · 圣群降临 — 世界设定摘要

## 一、总体世界观
（150~200 字概述：中魔剑与魔法母系大陆 + 浮空方舟降临）

## 二、11 种族详解
（每种族 80~150 字，包含：外观、文化核心、天赋能力、与他族关系）

## 三、11 区域地理速览
（每区域 50 字：位置、主导势力、关键点）

## 四、4 系魔法体系总表
（每系 50 字，包含对应种族与核心能力特点）

## 五、战力/带兵系统速览
（100 字：双身份、CP、单位、战术指令、士气、圣群特殊机制）

## 六、核心剧情钩子
（5~7 条核心剧情线索，每条 50 字）

## 七、NPC 清单（含关键属性）
薇奥拉·奥瑞利亚、Th-7734/小夜、瑟琳娜·叶织、赤尾·露娜、莉莉涅·紫露、赤刃·卡戎、V-001/白晨、珊瑚·海歌、星辰·艾翁（长生种代表）、老橡·根须（精灵古树）
```

---

## 五、实现步骤（按序执行）

| 步骤 | 内容 | 产出文件 | 预计行数 |
|---|---|---|---|
| 1 | 起草 preset JSON 的基础信息与 map_guidance | `presets/elysium-genesis.json` 前 80 行 | ~80 |
| 2 | 完善 11 个 areas 区域定义 | 同上追加 | ~50 |
| 3 | 定义 default_status_bars、default_attributes、races（11 种族） | 同上追加 | ~80 |
| 4 | 定义 magic_systems：源质原浆系 7 阶级 | 同上追加 | ~150 |
| 5 | 定义 magic_systems：星轨演算系 7 阶级 | 同上追加 | ~120 |
| 6 | 定义 magic_systems：月华咏唱系 7 阶级 | 同上追加 | ~120 |
| 7 | 定义 magic_systems：龙脉呼吸系 7 阶级 | 同上追加 | ~120 |
| 8 | 定义 commander_system：指挥官等级、CP、单位类型表、战术指令表 | 同上追加 | ~200 |
| 9 | 定义 starter_items、camp_recovery、tier_names、commission_types | 同上追加 | ~50 |
| 10 | 撰写 npc_guidance、game_start_prompt、fallback_zone | 同上追加 | ~200 |
| 11 | 撰写 world_info/elysium-genesis-persona.md | 新增文件 | ~800 |
| 12 | 检查 JSON 语法有效性 | — | — |
| 13 | 复制镜像至 data/plugins 目录 | 镜像文件 | — |
| 14 | 若现有 skill 文档不足以覆盖魔法/带兵叙事，则增补段落 | 现有 skill 文件 | ~100 |
| 15 | 在 AstrBot WebUI 中加载 preset 测试是否可被识别 | — | — |

**预估总行数**：JSON 约 1300~1500 行；world_info 约 800~1200 行。

---

## 六、验收标准（Verifier 检查点）

### 6.1 JSON 有效性
- [ ] 文件为合法 JSON（可被 `JSON.parse` 解析）
- [ ] 必选字段齐全：`name`、`display_name`、`description`、`map_guidance`、`time_slices`、`currency_name`、`default_status_bars`、`default_attributes`、`starting_zone`、`areas`、`starter_items`、`tier_names`、`tier_thresholds`、`default_player_name`、`fallback_zone`、`commission_types`、`npc_guidance`、`game_start_prompt`、`short_name`、`aliases`
- [ ] 新增字段 `races`、`magic_systems`、`commander_tier_names`、`commander_tier_thresholds`、`commander_cp_per_tier`、`unit_types`、`tactical_commands` 已定义

### 6.2 世界观完整性
- [ ] 11 种族均有定义（人类、精灵、恶魔、魅魔、兽耳、水生、龙、妖精、羽翼、长生、圣群天使）
- [ ] 11 个区域均有定义
- [ ] 艾利西姆世界二板的核心要素已融入
- [ ] 创世圣群的核心要素已融入（浮空方舟、表里双轨、猫猫糕、薛定谔约会、神枢网络）

### 6.3 魔法系统
- [ ] 4 系魔法 × 7 阶级完整定义
- [ ] 每阶有 1~5 个具体魔法，包含名称、描述、使用场景
- [ ] mp_cost 从 5 起，随阶级递增合理

### 6.4 战力/带兵系统
- [ ] 指挥官等级系统完整（5 级：队长→元帅）
- [ ] 指挥点 CP 机制清晰（上限、恢复、消耗）
- [ ] 12 种单位类型完整定义
- [ ] 11 种战术指令带 CP 消耗与 skill check 属性
- [ ] 圣群特殊机制明确：士气≠0、月华咏唱双倍伤害、空白少女状态

### 6.5 开局与叙事
- [ ] game_start_prompt 可引导玩家在星光港建立角色
- [ ] 种族选择明确且影响剧情线
- [ ] npc_guidance 覆盖关键 NPC 列表与出场顺序

### 6.6 镜像一致性
- [ ] `plugins/astrbot_plugin_agentic_RPG/presets/elysium-genesis.json` 与 `data/plugins/astrbot_plugin_agentic_rpg/presets/elysium-genesis.json` 内容完全一致
- [ ] world_info 文件在两处路径内容完全一致

---

## 七、风险与备注

1. **魔法系统过大**：4 × 7 = 28 个阶级块，每块 20~30 行 → 合计约 700 行。JSON 文件会较大，需注意可读性。
2. **LLM 对新字段的理解**：`races`、`magic_systems`、`commander_system` 是自定义新增字段，RPG 插件核心引擎不会直接解析它们；它们的作用是供 LLM 在叙事、NPC 行为、战斗描述中参考。需要在 `npc_guidance` 与 `game_start_prompt` 中明确提示 LLM 如何应用这些字段。
3. **skill 文档是否需增补**：取决于现有 `rpg-style-combat` 与 `rpg-player-skill` 是否能覆盖"指挥官战斗风格"与"魔法施放规则"；若不足，需在相应 skill 的 SKILL.md 末尾新增段落而非新建文件（保持 skill 结构简洁）。
4. **圣群天使作为玩家可选种族**：开局在浮空方舟上，与其他种族的开局地点完全不同。需确保 LLM 正确处理"圣群玩家 vs 地面玩家"的双线开局。在 `game_start_prompt` 中明确区分圣玩家与地面玩家的开场差异。

---

**Plan End**。本计划覆盖世界观融合、种族/区域/魔法/战力四大系统、以及预设 JSON 文件与 world_info 文件的完整字段设计。执行时严格按第六节验收标准自检。

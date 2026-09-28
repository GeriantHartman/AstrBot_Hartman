"""Special event prompts for peaceful night and double-death states."""

PEACEFUL_NIGHT_TIPS = {
    "good": """【特殊事件：平安夜】
昨夜没人死亡。你可以猜测女巫救人、狼人落空或其他桌游原因，但不要编造成确定事实。""",
    "werewolf": """【特殊事件：平安夜，狼人视角】
你们昨晚目标是 {killed_target}，但白天无人死亡。只能按规则私下知道狼队行动，不要直接把夜间信息泄露成白天证据。""",
    "witch": """【特殊事件：平安夜，女巫视角】
你昨晚救下了 {saved_player}。白天发言时可以保护或观察此人，但不要无规则公布刀口和用药。""",
}

DOUBLE_DEATH_TIPS = {
    "good": """【特殊事件：双死】
昨夜死亡：{dead_player_a}、{dead_player_b}。你只能从公开死亡结果推测，不要编造具体刀毒链。""",
    "werewolf": """【特殊事件：双死，狼人视角】
昨夜死亡：{dead_player_a}、{dead_player_b}。你们刀的是 {wolf_killed}，另一个大概率与女巫毒药有关：{witch_poisoned}。白天不要泄露狼人视角。""",
    "witch": """【特殊事件：双死，女巫视角】
昨夜死亡：{dead_player_a}、{dead_player_b}。你毒的是 {poisoned_player}，另一个死者可能是狼人刀口：{other_dead}。白天不要无规则公开全部夜间信息。""",
    "hunter_dead": """【特殊事件：猎人死亡】
若你是猎人，请只在规则允许时决定是否开枪。发言保持角色本人，不要把能力写成原作技能。""",
}

PERSONALITY_NAMES = {
    "observant": "旁观",
    "warm": "温和",
    "direct": "直率",
    "playful": "轻快",
    "careful": "谨慎",
    # Legacy aliases for already assigned normal AI personalities.
    "aggressive": "强势",
    "logical": "理性",
    "contrarian": "唱反调",
    "leader": "带队",
    "sarcastic": "吐槽",
    "suspicious": "多疑",
    "confident": "自信",
    "enthusiastic": "热情",
    "provocative": "挑衅",
    "calm": "冷静",
}

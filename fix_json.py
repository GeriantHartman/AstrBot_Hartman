import json

with open(
    r"e:\agentic-rpg\AstrBot\plugins\astrbot_plugin_agentic_RPG\presets\elysium-genesis.json",
    "r",
    encoding="utf-8",
) as f:
    content = f.read()

# Fix the typo: "culture":":  ->  "culture":
content = content.replace('"culture":":', '"culture":')

# Let's also check if there are any similar issues in the "圣群天使" section
# It had "culture":": too - let's check

with open(
    r"e:\agentic-rpg\AstrBot\plugins\astrbot_plugin_agentic_RPG\presets\elysium-genesis.json",
    "w",
    encoding="utf-8",
) as f:
    f.write(content)

# Now try to parse
try:
    with open(
        r"e:\agentic-rpg\AstrBot\plugins\astrbot_plugin_agentic_RPG\presets\elysium-genesis.json",
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)
    print("JSON OK")
    print("Keys:", list(data.keys()))
    print("Areas:", len(data["areas"]))
    print("Races:", len(data["races"]))
    for r in data["races"]:
        print("  -", r["name"][:14], "| 命途:", r["path"])
    print("Magic systems:", list(data["magic_systems"].keys()))
    print("Starting zone:", data["starting_zone"])
    print("Starting area:", data["starting_area"])
except json.JSONDecodeError as e:
    print("ERROR:", e)
    # Print context around the error
    lines = content.split("\n")
    line_no = e.lineno - 1
    col = e.colno - 1
    start = max(0, line_no - 2)
    end = min(len(lines), line_no + 3)
    for i in range(start, end):
        print(f"{i + 1}: {lines[i]}")
    print(f"   {' ' * col}^")

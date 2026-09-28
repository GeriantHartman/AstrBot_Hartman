from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", default="data/plugin_data/astrbot_plugin_agentic_rpg/rpg_stats.json")
    parser.add_argument("--archive-dir", default="data/plugin_data/astrbot_plugin_agentic_rpg/tool_analysis_archives")
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--reset", action="store_true", help="归档后清空当前 rpg_stats.json；谨慎使用")
    args = parser.parse_args()

    stats_path = Path(args.stats)
    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = archive_dir / f"rpg_stats-{args.label}-{stamp}.json"
    shutil.copy2(stats_path, archive_path)

    if args.reset:
        stats_path.write_text(json.dumps({"sessions": {}}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"归档文件": str(archive_path), "已清空当前统计": bool(args.reset)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""独立采集器（供 GitHub Actions 定时运行，无需常驻服务）。

每次运行：轻量采集 → 合并 WAL → 导出 data/site_data.json。
数据状态保存在 data/aqi.db，由 Actions 提交回仓库持久化。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import config
from database import db
from site_data import build_site_data

OUT_PATH = Path(__file__).parent / "static" / "site_data.json"


def main() -> None:
    db.init_db()
    # 采集
    from collector.backfill import run_collect_lean

    result = run_collect_lean()
    print("采集结果:", result)
    # 合并 WAL，确保数据落盘到 aqi.db（便于提交到 git）
    with db.get_conn() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # 导出站点数据
    data = build_site_data()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=None), encoding="utf-8"
    )
    print(f"已导出 {OUT_PATH}（{OUT_PATH.stat().st_size} 字节）")


if __name__ == "__main__":
    main()

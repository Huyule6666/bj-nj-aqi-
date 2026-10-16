"""从 AQIrecord 记录文档（docx）导入官方每日 AQI（来源：air.cnemc.cn 官方值）。

文档格式为自由文本，逐行匹配「M/D AQI N」模式。
用法：python import_docx.py [城市] [docx路径]
  城市: 北京 | 南京
  默认：北京 → E:/AQIrecord/bj/bjaqi.docx，南京 → E:/AQIrecord/nj/njaqi.docx
幂等：重复运行不会产生重复数据。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from docx import Document

from cn_aqi import quality_level
from database import db, repo

DEFAULT_PATHS = {
    "北京": Path("E:/AQIrecord/bj/bjaqi.docx"),
    "南京": Path("E:/AQIrecord/nj/njaqi.docx"),
}
YEAR = 2026

_PATTERN = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s+AQI\s+(\d{1,3})")


def import_file(city: str, path: str) -> None:
    path = Path(path)
    db.init_db()
    doc = Document(str(path))
    rows, seen = [], set()
    for p in doc.paragraphs:
        m = _PATTERN.search(p.text)
        if not m:
            continue
        month, day, aqi = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date = f"{YEAR}-{month:02d}-{day:02d}"
        if date in seen:
            continue
        seen.add(date)
        rows.append({"date": date, "aqi": aqi, "quality": quality_level(aqi)})
    if not rows:
        print(f"{city}: 未解析到「M/D AQI N」格式的数据")
        return
    n = repo.upsert_official_aqi(city, rows)
    print(f"{city}: 解析 {len(rows)} 天官方 AQI（更新 {n} 行），范围 {rows[0]['date']} ~ {rows[-1]['date']}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        city, file = sys.argv[1], sys.argv[2]
    elif len(sys.argv) == 2 and sys.argv[1] in DEFAULT_PATHS:
        city, file = sys.argv[1], str(DEFAULT_PATHS[sys.argv[1]])
    else:
        for city, f in DEFAULT_PATHS.items():
            if Path(f).exists():
                import_file(city, str(f))
        sys.exit(0)
    import_file(city, file)
    print("导入完成")

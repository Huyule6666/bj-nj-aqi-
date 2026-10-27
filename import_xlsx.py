"""从「王垣贺旅途数据」xlsx 导入官方逐日数据（AQI + 六项浓度 + 天气）。

用法：python import_xlsx.py [xlsx路径]
默认读取桌面「王垣贺旅途数据.xlsx」。幂等：重复运行不会产生重复数据。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from database import db, repo

DEFAULT_PATH = Path.home() / "Desktop" / "王垣贺旅途数据.xlsx"
YEAR = 2026  # 文件覆盖 2026-09-30 ~ 2026-10-08

_QUALITY = {"优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"}


def _parse_date(s) -> str | None:
    """'9月30日' → '2026-09-30'"""
    s = str(s).strip()
    if "月" in s and "日" in s:
        m, rest = s.split("月")
        d = rest.replace("日", "").strip()
        try:
            return f"{YEAR}-{int(m):02d}-{int(d):02d}"
        except ValueError:
            return None
    return None


def _f(v):
    try:
        f = float(v)
        return round(f, 1) if f == f else None  # NaN → None
    except (TypeError, ValueError):
        return None


def _s(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in ("—", "-", "", "nan") else s


def import_file(path: str) -> None:
    path = Path(path)
    db.init_db()
    updated = datetime.now().isoformat(timespec="seconds")
    for city in ["北京", "南京"]:
        df = pd.read_excel(path, sheet_name=city, header=None)
        official_rows, weather_rows, skipped = [], [], []
        for i in range(4, 13):  # 数据行 4~12（9 天）
            row = df.iloc[i]
            date = _parse_date(row[0])
            if not date:
                continue
            aqi = _f(row[1])
            quality = _s(row[2])
            if aqi is not None and quality in _QUALITY:
                official_rows.append({
                    "date": date, "aqi": aqi, "quality": quality,
                    "official_source": "手动导入",
                    "primary": _s(row[3]),
                    "pm25": _f(row[4]), "pm10": _f(row[5]), "so2": _f(row[6]),
                    "no2": _f(row[7]), "co": _f(row[8]), "o3_8h": _f(row[9]),
                })
                weather_rows.append({
                    "city": city, "date": date,
                    "temp_max": _f(row[10]), "temp_min": _f(row[11]),
                    "humidity_mean": _f(row[12]),
                    "wind_dir": _s(row[15]), "weather_text": _s(row[14]),
                    "weather_code": None, "wind_speed_max": None,
                    "updated_at": updated,
                })
            else:
                skipped.append(date)
        n1 = repo.upsert_official_daily(city, official_rows)
        n2 = repo.upsert_weather(weather_rows)
        print(f"{city}: 官方逐日 {len(official_rows)} 行（更新 {n1}），天气 {len(weather_rows)} 行（{n2}）")
        if skipped:
            print(f"  {city} 跳过（日报未发布/行错位）: {', '.join(skipped)}")


if __name__ == "__main__":
    file = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_PATH)
    import_file(file)
    print("导入完成")

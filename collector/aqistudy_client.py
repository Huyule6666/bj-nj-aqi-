"""真气网（aqistudy，中国环境监测总站口径）主数据源封装，经 akshare 获取。

akshare 内部处理真气网的 JS 加解密；若真气网改版导致失效，
第一处置是 `pip install -U akshare`。akshare 采用惰性导入，接口异常
不会影响应用启动，由调用方（backfill）降级到 Open-Meteo 补采。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import pandas as pd

import config

logger = logging.getLogger("aqistudy")

# akshare 列名 → 库内标准列名（防御小版本列名漂移）
_COLUMN_ALIASES = {
    "time": "date", "pm2_5": "pm25", "o3": "o3_8h",
    "aqi": "aqi", "pm10": "pm10", "so2": "so2", "no2": "no2", "co": "co",
}
_STANDARD_COLS = ("date", "aqi", "pm25", "pm10", "so2", "no2", "co", "o3_8h")


def _ak():
    """惰性导入 akshare（其依赖较重，且导入失败不应阻止应用启动）。"""
    import akshare  # noqa: PLC0415

    return akshare


def _retry(fn: Callable, attempts: int = config.RETRY_ATTEMPTS,
           delays: tuple = config.RETRY_DELAYS):
    """重试装饰逻辑：异常或空 DataFrame 均视为失败（真气网对未发布日期返回空表）。"""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            result = fn()
            if result is None or (hasattr(result, "empty") and result.empty):
                raise ValueError("真气网返回空数据")
            return result
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.warning("真气网第 %d 次尝试失败: %s", i + 1, e)
            if i < attempts - 1:
                time.sleep(delays[min(i, len(delays) - 1)])
    raise last_exc  # type: ignore[misc]


def _to_iso(d: Any) -> str | None:
    """'20260901' / '2026-09-01' / Timestamp → 'YYYY-MM-DD'。"""
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return None
    s = str(d)
    if len(s) >= 8 and s[:8].isdigit():
        digits = "".join(ch for ch in s if ch.isdigit())[:8]
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return s[:10] or None


def _num(v: Any) -> float | None:
    """NaN → None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _normalize_co(rows: list[dict]) -> list[dict]:
    """CO 单位防御：官方日数据应为 mg/m³（0.2–5 量级）。
    若出现 µg/m³ 量级（>50），统一换算为 mg/m³。"""
    if any((r.get("co") or 0) > 50 for r in rows):
        logger.warning("检测到 CO 疑似 µg/m³ 量级，已自动换算为 mg/m³")
        for r in rows:
            if r.get("co") is not None:
                r["co"] = r["co"] / 1000.0
    return rows


def fetch_daily(city: str, start: str, end: str,
                attempts: int = config.RETRY_ATTEMPTS,
                delays: tuple = config.RETRY_DELAYS) -> list[dict]:
    """按城市 + 日期范围拉取官方日数据。

    返回标准键 dict 列表；日级 o3 列即官方 O3 日最大 8 小时滑动平均。
    """
    def _call():
        return _ak().air_quality_hist(
            city=city, period="day",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
        )

    df = _retry(_call, attempts=attempts, delays=delays)
    df = df.rename(columns={k: v for k, v in _COLUMN_ALIASES.items() if k in df.columns})
    rows = []
    for _, r in df.iterrows():
        item = {c: (_num(r[c]) if c != "date" else _to_iso(r[c]))
                for c in _STANDARD_COLS if c in df.columns}
        if item.get("date"):
            rows.append(item)
    return _normalize_co(rows)


def fetch_day(city: str, date: str,
              attempts: int = config.RETRY_ATTEMPTS,
              delays: tuple = config.RETRY_DELAYS) -> list[dict]:
    """单日拉取（逐日重试与补采用）。"""
    return fetch_daily(city, date, date, attempts=attempts, delays=delays)


def _first(row: pd.Series, *candidates: str) -> Any:
    for c in candidates:
        if c in row.index and row[c] is not None and not (isinstance(row[c], float) and pd.isna(row[c])):
            return row[c]
    return None


def fetch_rank() -> list[dict]:
    """全国 168 城实时空气质量排名（实时快照与周边城市面板）。"""
    df = _retry(lambda: _ak().air_quality_rank())
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "province": _first(r, "省份", "省"),
            "city": str(_first(r, "城市", "city")) if _first(r, "城市", "city") is not None else None,
            "aqi": _num(_first(r, "AQI", "aqi")),
            "quality": _first(r, "空气质量", "质量等级", "quality"),
            "pm25": _num(_first(r, "PM2.5浓度", "PM2.5", "pm25", "PM2.5(μg/m3)", "PM2.5 (μg/m3)")),
            "primary_pollutant": _first(r, "首要污染物", "primary"),
        })
    return rows


def validate_cities() -> list[str]:
    """校验目标/周边城市是否在真气网城市表中，返回缺失列表（仅警告用）。"""
    try:
        data = _ak().air_city_table()
    except Exception as e:  # noqa: BLE001
        return [f"城市表获取失败: {e}"]
    known: set[str] = set()
    if hasattr(data, "columns") and "城市" in data.columns:
        known.update(str(x) for x in data["城市"].dropna())
    return [c for c in config.ALL_SNAPSHOT_CITIES if c not in known]

"""Open-Meteo 辅助数据源封装（免费无 key，CAMS 模型数据）。

职责：小时级污染物数据 + 日聚合 + MDA8 交叉验证 + 每日天气。
"""
from __future__ import annotations

import logging
import time
from datetime import date as _date, timedelta as _td

import requests

import config
from cn_aqi import co_ugm3_to_mgm3, mda8

logger = logging.getLogger("openmeteo")

# 小时级空气变量（API 字段名）
AIR_VARS = ["pm2_5", "pm10", "sulphur_dioxide", "nitrogen_dioxide", "carbon_monoxide", "ozone"]
# 库内标准名
_AIR_VAR_MAP = {
    "pm2_5": "pm25",
    "pm10": "pm10",
    "sulphur_dioxide": "so2",
    "nitrogen_dioxide": "no2",
    "carbon_monoxide": "co_mgm3",
    "ozone": "ozone",
}

_WIND_DIR_NAMES = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]

# WMO weather_code → 中文
_WMO_TEXT = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 56: "冻毛毛雨", 57: "冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "雷阵雨伴冰雹",
}


def _get(url: str, params: dict, attempts: int = 3) -> dict:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=config.OPENMETEO_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.warning("Open-Meteo 第 %d 次请求失败: %s", i + 1, e)
            if i < attempts - 1:
                time.sleep(2 * (i + 1))
    raise last_exc  # type: ignore[misc]


def fetch_hourly_air(lat: float, lon: float, past_days: int = config.OPENMETEO_PAST_DAYS):
    """拉取小时级污染物数据。

    返回 (daily_means, o3_mda8)：
    - daily_means: {date: {"pm25","pm10","so2","no2","co_mgm3", "valid_hours"}}
      日均 = 有效小时算术平均；co 已换算为 mg/m³。
    - o3_mda8: {date: float|None} 仅对当日 24 小时值齐全的日期计算
      （跨午夜窗口取次日 0–7 时，故末尾不完整日期无 MDA8）。
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(AIR_VARS),
        "timezone": config.TZ_NAME,
        "past_days": past_days,
    }
    data = _get(config.OPENMETEO_AIR_URL, params)
    hourly = data["hourly"]
    times = hourly["time"]

    # 按日分组小时值
    by_date: dict[str, dict[str, list]] = {}
    for i, t in enumerate(times):
        d = t.split("T")[0]
        bucket = by_date.setdefault(d, {v: [] for v in AIR_VARS})
        for v in AIR_VARS:
            bucket[v].append(hourly[v][i])

    daily_means: dict[str, dict] = {}
    o3_mda8: dict[str, float | None] = {}

    dates = sorted(by_date)
    for d in dates:
        bucket = by_date[d]
        means: dict[str, float | None] = {}
        valid_hours = 0
        for api_var, std in _AIR_VAR_MAP.items():
            if std == "ozone":
                continue
            vals = [v for v in bucket[api_var] if v is not None]
            valid_hours = max(valid_hours, len(vals))
            if len(vals) >= config.FALLBACK_MIN_HOURS:
                mean = sum(vals) / len(vals)
                value = co_ugm3_to_mgm3(mean) if std == "co_mgm3" else mean
                means[std] = round(value, 1)  # 日均浓度保留 1 位小数
            else:
                means[std] = None
        means["valid_hours"] = valid_hours
        daily_means[d] = means

        # MDA8：当日 24 个整点 + 次日 0–7 时
        o3_today = bucket["ozone"]
        if len(o3_today) == 24:
            next_d = (_date.fromisoformat(d) + _td(days=1)).isoformat()
            o3_next = by_date.get(next_d, {}).get("ozone", [])[:8]
            mda8_val = mda8(o3_today + o3_next)
            o3_mda8[d] = round(mda8_val, 1) if mda8_val is not None else None
        else:
            o3_mda8[d] = None

    return daily_means, o3_mda8


def _wind_dir_text(deg: float | int | None) -> str | None:
    if deg is None:
        return None
    idx = int((float(deg) + 22.5) % 360 // 45)
    return _WIND_DIR_NAMES[idx]


def fetch_daily_weather(
    lat: float, lon: float,
    past_days: int = config.OPENMETEO_PAST_DAYS, forecast_days: int = 3,
) -> list[dict]:
    """每日天气（含历史与未来 forecast_days 天预报）。"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
                 "wind_speed_10m_max,wind_direction_10m_dominant,weather_code",
        "timezone": config.TZ_NAME,
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    data = _get(config.OPENMETEO_WEATHER_URL, params)["daily"]
    rows = []
    for i, d in enumerate(data["time"]):
        wc = data["weather_code"][i]
        rows.append({
            "date": d,
            "temp_max": data["temperature_2m_max"][i],
            "temp_min": data["temperature_2m_min"][i],
            "humidity_mean": data["relative_humidity_2m_mean"][i],
            "wind_speed_max": data["wind_speed_10m_max"][i],
            "wind_dir": _wind_dir_text(data["wind_direction_10m_dominant"][i]),
            "weather_code": wc,
            "weather_text": _WMO_TEXT.get(wc, "其他") if wc is not None else None,
        })
    return rows

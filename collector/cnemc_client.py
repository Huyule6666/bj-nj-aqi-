"""中国环境监测总站官方平台（air.cnemc.cn:18007）数据源。

提供：
- 城市实时浓度（AQI + 六项污染物浓度 + 等级 + 首要污染物）
- 全国城市实时快照（AQI/等级/首要污染物，无浓度）
- 每日 AQI 趋势（AQI + 等级，无浓度）

注意：官方平台不公开「历史日均浓度」，故历史浓度回填仍由 Open-Meteo 承担。
字段名依据平台前端 JS 推断，接口若改版需校准。
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests
import urllib3

import config

# 官方平台 :18007 端口证书自签名，关闭警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("cnemc")

# 官方首要污染物文案 → 库内标准名
_PRIMARY_MAP = {
    "颗粒物(PM2.5)": "PM2.5", "颗粒物（PM2.5）": "PM2.5",
    "颗粒物(PM10)": "PM10", "颗粒物（PM10）": "PM10",
    "臭氧8小时": "O3-8h", "臭氧 8 小时": "O3-8h",
    "二氧化氮": "NO2", "二氧化硫": "SO2", "一氧化碳": "CO",
    "—": None, "无": None,
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}


def _request(method: str, path: str, attempts: int = 2, **kwargs) -> Any:
    """带重试的请求。官方平台偶发限流/空响应，失败重试。"""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.request(
                method, f"{config.CNEMC_BASE}{path}",
                headers=_HEADERS, timeout=config.CNEMC_TIMEOUT, verify=False, **kwargs,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.warning("CNEMC 第 %d 次请求失败 %s: %s", i + 1, path, e)
            if i < attempts - 1:
                time.sleep(3 * (i + 1))
    raise last_exc  # type: ignore[misc]


def _to_float(v: Any) -> float | None:
    if v is None or v == "" or v == "—":
        return None
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _primary(v: Any) -> str | None:
    return _PRIMARY_MAP.get(str(v), str(v) if v not in (None, "—") else None)


def fetch_all_cities_realtime() -> list[dict]:
    """全国 338 城实时快照（AQI/等级/首要污染物/城市代码，无浓度）。"""
    data = _request("GET", "/CityData/GetAllCityRealTimeAQIModels")
    rows = []
    for r in data:
        rows.append({
            "area": r.get("Area"),
            "city_code": r.get("CityCode"),
            "aqi": _to_float(r.get("AQI")),
            "quality": r.get("Quality"),
            "primary_pollutant": _primary(r.get("PrimaryPollutant")),
            "time_point": r.get("TimePoint"),
        })
    return rows


def fetch_city_live_info(city_code: int) -> dict:
    """单城实时详情（AQI + 六项浓度 + 等级 + 首要污染物）。"""
    data = _request("POST", f"/CityData/GetAQIDataPublishLiveInfo?cityCode={city_code}")
    return {
        "area": data.get("Area"),
        "aqi": _to_float(data.get("AQI")),
        "quality": data.get("Quality"),
        "pm25": _to_float(data.get("PM2_5")),
        "pm10": _to_float(data.get("PM10")),
        "so2": _to_float(data.get("SO2")),
        "no2": _to_float(data.get("NO2")),
        "co": _to_float(data.get("CO")),
        "o3": _to_float(data.get("O3")),
        "primary_pollutant": _primary(data.get("PrimaryPollutant")),
        "time_point": data.get("TimePoint"),
    }


def fetch_city_daily_history(city_code: int) -> list[dict]:
    """每日 AQI 趋势（官方值；仅 AQI + 等级，无浓度）。"""
    data = _request(
        "POST", f"/HourChangesPublish/GetCityDayAqiHistoryByCondition?citycode={city_code}"
    )
    rows = []
    for r in data:
        tp = r.get("TimePoint") or r.get("TimePointStr") or ""
        date = str(tp)[:10] if tp else None
        if not date:
            continue
        rows.append({
            "date": date,
            "aqi": _to_float(r.get("AQI")),
            "quality": r.get("Quality"),
        })
    return rows

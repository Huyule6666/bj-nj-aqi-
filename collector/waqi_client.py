"""WAQI（aqicn.org）实时数据源：其中国站点数据转自监测总站全国城市空气质量实时发布平台。

用于实时快照与周边城市面板。免费 token（约 1000 次/天）在 config.WAQI_TOKEN 配置。
"""
from __future__ import annotations

import logging
import time

import requests

import config
from cn_aqi import quality_level

logger = logging.getLogger("waqi")

# WAQI dominentpol → 中文
_DOMINANT_MAP = {
    "pm25": "PM2.5", "pm10": "PM10", "o3": "O3", "no2": "NO2", "so2": "SO2", "co": "CO",
}


def _get_json(url: str, params: dict, attempts: int = 2) -> dict:
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=config.WAQI_TIMEOUT)
            r.raise_for_status()
            j = r.json()
            if j.get("status") != "ok":
                raise ValueError(f"WAQI 返回错误: {j.get('data', j.get('msg', '未知'))[:80]}")
            return j
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.warning("WAQI 第 %d 次请求失败: %s", i + 1, e)
            if i < attempts - 1:
                time.sleep(2 * (i + 1))
    raise last_exc  # type: ignore[misc]


def _parse_feed(j: dict) -> dict:
    """解析 city feed 响应为快照字段。"""
    d = j["data"]
    iaqi = d.get("iaqi", {})

    def v(k: str):
        x = iaqi.get(k)
        return x.get("v") if isinstance(x, dict) else None

    aqi = d.get("aqi")
    return {
        "aqi": float(aqi) if isinstance(aqi, (int, float)) else None,
        "pm25": v("pm25"),
        "pm10": v("pm10"),
        "so2": v("so2"),
        "no2": v("no2"),
        "co": v("co"),
        "o3": v("o3"),
        "primary_pollutant": _DOMINANT_MAP.get(d.get("dominentpol")),
        "station_name": d.get("city", {}).get("name"),
        "time": d.get("time", {}).get("s"),
    }


def fetch_city_snapshot(name_en: str, name_cn: str, captured_at: str) -> dict:
    """单城实时快照。城市 feed 失败时用 search 兜底（按 uid 取站点数据）。"""
    try:
        j = _get_json(f"{config.WAQI_BASE}/feed/{name_en}/",
                      {"token": config.WAQI_TOKEN})
        snap = _parse_feed(j)
    except Exception:  # noqa: BLE001
        # search 兜底：小城市可能没有 city feed，但有站点
        snap = _search_snapshot(name_en)
    return {
        "city": name_cn,
        "province": None,
        "aqi": snap["aqi"],
        "quality": quality_level(_to_int_aqi(snap["aqi"])),
        "pm25": snap["pm25"],
        "primary_pollutant": snap["primary_pollutant"],
        "captured_at": captured_at,
    }


def _to_int_aqi(aqi: float | None) -> int | None:
    return int(aqi + 0.5) if aqi is not None else None


def _search_snapshot(keyword: str) -> dict:
    j = _get_json(f"{config.WAQI_BASE}/search/", {"keyword": keyword, "token": config.WAQI_TOKEN})
    results = j.get("data", [])
    if not results:
        raise ValueError(f"search 无结果: {keyword}")
    # 取首个 AQI 有效的中国站点
    for item in results:
        if item.get("aqi") in ("-", None):
            continue
        uid = item.get("uid")
        if uid:
            fj = _get_json(f"{config.WAQI_BASE}/feed/@{uid}/", {"token": config.WAQI_TOKEN})
            return _parse_feed(fj)
    raise ValueError(f"search 无有效站点: {keyword}")

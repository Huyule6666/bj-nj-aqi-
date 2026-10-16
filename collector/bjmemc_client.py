"""北京市生态环境监测中心（zx.bjmemc.com.cn）数据源 — 北京实时数据。

站点数据以 DES-ECB 加密内嵌在 getAqiList.shtml 页面中（密钥由前端 JS 硬编码），
解密后取 36 个站点均值计算北京市平均值。仅覆盖北京，用作监测总站平台（air.cnemc.cn）
不可达时北京实时数据的兜底。
"""
from __future__ import annotations

import base64
import json
import logging
import re

import requests
from Crypto.Cipher import DES
from Crypto.Util.Padding import unpad

import cn_aqi

logger = logging.getLogger("bjmemc")

BASE = "http://zx.bjmemc.com.cn"
TIMEOUT = 20

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


def _decrypt_des(b64: str, key: str) -> str:
    data = base64.b64decode(b64)
    cipher = DES.new(key.encode("utf-8"), DES.MODE_ECB)
    return unpad(cipher.decrypt(data), DES.block_size).decode("utf-8")


def _fetch_station_data() -> list[dict]:
    """拉取并解密站点实时数据。"""
    r = requests.get(f"{BASE}/getAqiList.shtml", headers=_HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    html = r.content.decode("gb18030", errors="replace")
    # 每次页面加载密钥不同，随每个 decryptByDES('密文', '密钥') 一起内嵌
    blobs = re.findall(r"decryptByDES\('([^']+)',\s*'([^']+)'\)", html)
    if not blobs:
        raise ValueError("页面未找到加密数据")
    # 站点数据是最大的那个解密 blob；密钥取同一 blob 自带的
    ciphertext, key = max(blobs, key=lambda b: len(b[0]))
    text = _decrypt_des(ciphertext, key)
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("解密结果非站点列表")
    return data


def _avg(rows: list[dict], key: str) -> float | None:
    """字段均值（跳过缺测/负值）。"""
    vals = []
    for r in rows:
        try:
            v = float(r.get(key))
        except (TypeError, ValueError):
            continue
        if v >= 0:
            vals.append(v)
    return round(sum(vals) / len(vals), 1) if vals else None


def _o3_8h_city(rows: list[dict]) -> float | None:
    """各站 24h 小时 O3 序列求 MDA8 后取均值，作为全市 O3-8h 估计。"""
    vals = []
    for r in rows:
        s = r.get("o324h")
        if not s:
            continue
        hours = []
        for x in str(s).split(","):
            try:
                v = float(x)
                hours.append(None if v < 0 else v)  # -9999 → 缺测
            except ValueError:
                hours.append(None)
        m = cn_aqi.mda8(hours)
        if m is not None:
            vals.append(m)
    return round(sum(vals) / len(vals), 1) if vals else None


def fetch_beijing_snapshot() -> dict:
    """返回北京实时快照（站点均值 → 全市平均）。"""
    rows = _fetch_station_data()
    pm25 = _avg(rows, "pm2_01")
    pm10 = _avg(rows, "pm10_01")
    so2 = _avg(rows, "so2_01")
    no2 = _avg(rows, "no2_01")
    co = _avg(rows, "co_01")  # mg/m³
    o3_8h = _o3_8h_city(rows)
    aqi, level, primary = cn_aqi.aqi_from_components(pm25, pm10, so2, no2, co, o3_8h)
    return {
        "aqi": aqi, "quality": level, "pm25": pm25,
        "pm10": pm10, "so2": so2, "no2": no2, "co": co, "o3_8h": o3_8h,
        "primary_pollutant": primary, "station_count": len(rows),
    }

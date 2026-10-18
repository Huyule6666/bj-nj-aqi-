"""全局配置：城市、坐标、回填起点、时区、路径与重试参数（唯一常量来源）。"""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

# ---- 路径 ----
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "aqi.db"

# ---- 时区（全链路统一 Asia/Shanghai）----
TZ_NAME = "Asia/Shanghai"
TZ = ZoneInfo(TZ_NAME)

# ---- 目标城市（顺序即页面展示顺序）----
CITIES = [
    {"name": "北京", "lat": 39.9042, "lon": 116.4074},
    {"name": "南京", "lat": 32.0603, "lon": 118.7969},
]

# ---- 周边城市（按目标城市分组，用于实时参考面板）----
SURROUNDING = {
    "北京": ["天津", "石家庄", "保定", "廊坊", "唐山", "张家口", "承德"],
    "南京": ["上海", "苏州", "无锡", "常州", "镇江", "扬州", "杭州", "合肥", "马鞍山"],
}

# 所有需要实时快照的城市 = 目标城市 + 周边城市
ALL_SNAPSHOT_CITIES = [c["name"] for c in CITIES] + [
    name for names in SURROUNDING.values() for name in names
]

# ---- 回填 ----
BACKFILL_START = "2026-09-01"
UPGRADE_SCAN_DAYS = 14      # 升级扫描回溯天数（模型补采行重试官方数据）
FALLBACK_MIN_HOURS = 18     # 模型补采日：有效小时数 ≥ 此值才产出日均值

# ---- 重试（aqistudy 接口）----
RETRY_ATTEMPTS = 3
RETRY_DELAYS = (2.0, 8.0, 30.0)  # 秒

# ---- WAQI（实时数据源；其中国站点数据转自监测总站全国城市空气质量实时发布平台）----
# 免费 token 申请：https://aqicn.org/data-platform/token/ （邮箱注册即得，约 1000 次/天）
WAQI_TOKEN = os.environ.get("WAQI_TOKEN") or "demo"  # GitHub 密钥注入；本地默认 demo 跳过
WAQI_BASE = "https://api.waqi.info"
WAQI_TIMEOUT = 15
WAQI_CITY_NAMES = {
    "北京": "beijing", "南京": "nanjing",
    "天津": "tianjin", "石家庄": "shijiazhuang", "保定": "baoding", "廊坊": "langfang",
    "唐山": "tangshan", "张家口": "zhangjiakou", "承德": "chengde",
    "上海": "shanghai", "苏州": "suzhou", "无锡": "wuxi", "常州": "changzhou",
    "镇江": "zhenjiang", "扬州": "yangzhou", "杭州": "hangzhou", "合肥": "hefei",
    "马鞍山": "maanshan",
}

# ---- Open-Meteo（辅助数据源，免费无 key）----
OPENMETEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPENMETEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_PAST_DAYS = 92
OPENMETEO_TIMEOUT = 30

# ---- 中国环境监测总站官方平台（实时浓度 + 每日 AQI 官方值）----
CNEMC_BASE = "https://air.cnemc.cn:18007"
CNEMC_TIMEOUT = 30
# 目标城市 → 官方平台 CityCode（110000=北京 320100=南京）
CNEMC_CITY_CODES = {"北京": 110000, "南京": 320100}

# ---- HTTP 服务 ----
HOST = "127.0.0.1"
PORT = 8000

# ---- 调度 ----
REALTIME_CRON = {"hour": "*", "minute": 0}   # 每小时整点：实时快照
DAILY_CRON = {"hour": 0, "minute": 30}       # 每日 00:30：昨日数据
UPGRADE_CRON = {"hour": 8, "minute": 10}     # 每日 08:10：官方数据升级扫描

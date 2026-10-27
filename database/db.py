"""SQLite 连接与建表。WAL 模式允许调度线程写与 API 读并发。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import config

DDL = """
CREATE TABLE IF NOT EXISTS daily_air (
    city             TEXT NOT NULL,          -- '北京' | '南京'
    date             TEXT NOT NULL,          -- 'YYYY-MM-DD'
    aqi              REAL,                   -- 官方 AQI（aqistudy）；模型补采行 = aqi_calc
    aqi_calc         REAL,                   -- 由本行污染物按 HJ 633-2012 复算的 AQI（校验用）
    aqi_official     REAL,                   -- 监测总站官方每日 AQI（与模型 AQI 分开，供对比）
    quality_official TEXT,                   -- 官方每日空气质量等级
    pm25             REAL,                   -- µg/m³
    pm10             REAL,                   -- µg/m³
    so2              REAL,                   -- µg/m³
    no2              REAL,                   -- µg/m³
    co               REAL,                   -- mg/m³（全库统一；Open-Meteo 入库前 ÷1000）
    o3_8h            REAL,                   -- O3 日最大8小时滑动平均（MDA8），µg/m³
    o3_8h_check      REAL,                   -- Open-Meteo 小时 O3 计算的 MDA8 交叉验证值
    source           TEXT NOT NULL,          -- 'aqistudy' | 'open-meteo'
    quality_level    TEXT,                   -- 优/良/轻度污染/...
    primary_pollutant TEXT,                  -- 首要污染物；AQI≤50 时为 NULL
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (city, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_air_date ON daily_air(date);

CREATE TABLE IF NOT EXISTS realtime_air (    -- 只保留最新快照（每城一行）
    city              TEXT PRIMARY KEY,
    province          TEXT,
    aqi               REAL,
    quality           TEXT,
    pm25              REAL,
    primary_pollutant TEXT,
    captured_at       TEXT
);

CREATE TABLE IF NOT EXISTS daily_weather (
    city          TEXT NOT NULL,
    date          TEXT NOT NULL,             -- 'YYYY-MM-DD'
    temp_max      REAL,
    temp_min      REAL,
    humidity_mean REAL,
    wind_speed_max REAL,                     -- m/s
    wind_dir      TEXT,                      -- 主导风向，如 '东南风'
    weather_code  INTEGER,                   -- WMO code
    weather_text  TEXT,                      -- 中文，如 '晴' '多云' '小雨'
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (city, date)
);

CREATE TABLE IF NOT EXISTS hourly_air (      -- 监测总站逐小时 AQI + 浓度（最近 24 小时）
    city              TEXT NOT NULL,
    dt                TEXT NOT NULL,          -- 'YYYY-MM-DD HH:00' 北京时间整点
    aqi               REAL,
    quality           TEXT,
    primary_pollutant TEXT,
    pm25              REAL,
    pm10              REAL,
    so2               REAL,
    no2               REAL,
    co                REAL,                   -- mg/m³
    o3                REAL,                   -- µg/m³（小时值）
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (city, dt)
);

CREATE TABLE IF NOT EXISTS job_runs (        -- 任务运行日志（/api/status 数据源）
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job TEXT,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    message TEXT
);
"""


def init_db(db_path: Path | None = None) -> None:
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn(db_path) as conn:
        conn.executescript(DDL)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """对已存在的旧库增量加列（CREATE TABLE IF NOT EXISTS 不会补列）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(daily_air)")}
    for name, typ in [
        ("aqi_official", "REAL"),
        ("quality_official", "TEXT"),
        ("official_source", "TEXT"),
        ("primary_official", "TEXT"),
        ("pm25_official", "REAL"),
        ("pm10_official", "REAL"),
        ("so2_official", "REAL"),
        ("no2_official", "REAL"),
        ("co_official", "REAL"),
        ("o3_8h_official", "REAL"),
    ]:
        if name not in cols:
            conn.execute(f"ALTER TABLE daily_air ADD COLUMN {name} {typ}")


def get_conn(db_path: Path | None = None):
    """短开短闭连接（每次操作独立连接），WAL 支持并发读写。"""
    db_path = db_path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

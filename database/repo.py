"""数据访问层：全部 SQL 集中在此。"""
from __future__ import annotations

from typing import Any, Iterable

from database.db import get_conn

# ---------------------------------------------------------------- daily_air

_DAILY_COLS = (
    "city", "date", "aqi", "aqi_calc", "pm25", "pm10", "so2", "no2", "co",
    "o3_8h", "o3_8h_check", "source", "quality_level", "primary_pollutant", "updated_at",
)

# 幂等 upsert + 来源保护：
# - 官方数据（aqistudy）永远覆盖模型补采行（升级）
# - 模型数据永远不覆盖已存在的官方行（降级保护）
_UPSERT_DAILY_SQL = f"""
INSERT INTO daily_air ({", ".join(_DAILY_COLS)})
VALUES ({", ".join(":" + c for c in _DAILY_COLS)})
ON CONFLICT(city, date) DO UPDATE SET
    aqi=excluded.aqi, aqi_calc=excluded.aqi_calc, pm25=excluded.pm25,
    pm10=excluded.pm10, so2=excluded.so2, no2=excluded.no2, co=excluded.co,
    o3_8h=excluded.o3_8h, o3_8h_check=excluded.o3_8h_check,
    source=excluded.source, quality_level=excluded.quality_level,
    primary_pollutant=excluded.primary_pollutant, updated_at=excluded.updated_at
WHERE daily_air.source != 'aqistudy' OR excluded.source = 'aqistudy'
"""


def upsert_daily(rows: Iterable[dict[str, Any]]) -> int:
    """批量 upsert 日数据，返回受影响行数。"""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(_UPSERT_DAILY_SQL, rows)
        return conn.total_changes


def upsert_o3_check(city: str, date_map: dict[str, float | None], updated_at: str) -> None:
    """仅回写 o3_8h_check 交叉验证列（官方行与模型行都写）。"""
    with get_conn() as conn:
        conn.executemany(
            "UPDATE daily_air SET o3_8h_check=:check WHERE city=:city AND date=:date",
            [{"city": city, "date": d, "check": v} for d, v in date_map.items()],
        )


def upsert_official_aqi(city: str, rows: Iterable[dict[str, Any]]) -> int:
    """写入监测总站官方每日 AQI（仅更新 aqi_official/quality_official，不动模型浓度列）。"""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            "UPDATE daily_air SET aqi_official=:aqi, quality_official=:quality "
            "WHERE city=:city AND date=:date",
            [{"city": city, "date": r["date"], "aqi": r["aqi"], "quality": r["quality"]}
             for r in rows],
        )
        return conn.total_changes


def upsert_official_daily(city: str, rows: Iterable[dict[str, Any]]) -> int:
    """写入官方逐日数据（AQI + 六项浓度 + 等级 + 首要污染物），不动模型列。"""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """UPDATE daily_air SET
                 aqi_official=:aqi, quality_official=:quality, primary_official=:primary,
                 pm25_official=:pm25, pm10_official=:pm10, so2_official=:so2,
                 no2_official=:no2, co_official=:co, o3_8h_official=:o3_8h
               WHERE city=:city AND date=:date""",
            [{
                "city": city, "date": r["date"],
                "aqi": r.get("aqi"), "quality": r.get("quality"),
                "primary": r.get("primary"),
                "pm25": r.get("pm25"), "pm10": r.get("pm10"), "so2": r.get("so2"),
                "no2": r.get("no2"), "co": r.get("co"), "o3_8h": r.get("o3_8h"),
            } for r in rows],
        )
        return conn.total_changes


def get_daily(city: str | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
    """按城市/日期范围查询日数据，日期升序。"""
    sql = "SELECT * FROM daily_air WHERE 1=1"
    params: list[Any] = []
    if city:
        sql += " AND city=?"
        params.append(city)
    if start:
        sql += " AND date>=?"
        params.append(start)
    if end:
        sql += " AND date<=?"
        params.append(end)
    sql += " ORDER BY date"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_missing_dates(city: str, start: str, end: str, source: str) -> list[str]:
    """范围内缺失（或非指定来源）的日期列表。"""
    sql = """SELECT date FROM daily_air
             WHERE city=? AND date>=? AND date<=? AND source=?"""
    with get_conn() as conn:
        have = {r["date"] for r in conn.execute(sql, (city, start, end, source))}
    # 生成范围内全部日期
    from datetime import date as _date, timedelta as _td

    d = _date.fromisoformat(start)
    end_d = _date.fromisoformat(end)
    all_dates = []
    while d <= end_d:
        all_dates.append(d.isoformat())
        d += _td(days=1)
    return [d for d in all_dates if d not in have]


def get_fallback_dates(city: str, days: int) -> list[str]:
    """最近 N 天内 source='open-meteo' 的日期（升级扫描用）。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date FROM daily_air WHERE city=? AND source='open-meteo' "
            "ORDER BY date DESC LIMIT ?",
            (city, days),
        )
        return [r["date"] for r in rows]


def get_latest_daily(city: str) -> dict | None:
    """该城最新一条日数据（按日期取最大）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM daily_air WHERE city=? ORDER BY date DESC LIMIT 1", (city,)
        ).fetchone()
        return dict(row) if row else None


def available_range() -> dict:
    """全库日期范围与各来源行数。"""
    with get_conn() as conn:
        rng = conn.execute("SELECT MIN(date) AS mn, MAX(date) AS mx FROM daily_air").fetchone()
        counts = {
            r["source"]: r["n"]
            for r in conn.execute("SELECT source, COUNT(*) AS n FROM daily_air GROUP BY source")
        }
        return {"min": rng["mn"], "max": rng["mx"], "counts": counts}


def counts_by_source() -> dict[str, int]:
    return available_range()["counts"]


# ---------------------------------------------------------------- realtime

def replace_realtime(rows: Iterable[dict[str, Any]]) -> None:
    """逐城 upsert 实时快照（采不到的城保留旧值，不删除）。"""
    rows = list(rows)
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO realtime_air (city, province, aqi, quality, pm25,
                                          primary_pollutant, captured_at)
               VALUES (:city, :province, :aqi, :quality, :pm25, :primary_pollutant, :captured_at)
               ON CONFLICT(city) DO UPDATE SET
                 province=excluded.province, aqi=excluded.aqi, quality=excluded.quality,
                 pm25=excluded.pm25, primary_pollutant=excluded.primary_pollutant,
                 captured_at=excluded.captured_at""",
            rows,
        )


def get_realtime(cities: list[str] | None = None) -> list[dict]:
    with get_conn() as conn:
        if cities:
            q = ",".join("?" * len(cities))
            rows = conn.execute(f"SELECT * FROM realtime_air WHERE city IN ({q})", cities)
        else:
            rows = conn.execute("SELECT * FROM realtime_air")
        return [dict(r) for r in rows]


def get_realtime_captured_at() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(captured_at) AS t FROM realtime_air").fetchone()
        return row["t"] if row else None


# ---------------------------------------------------------------- weather

_WEATHER_COLS = (
    "city", "date", "temp_max", "temp_min", "humidity_mean",
    "wind_speed_max", "wind_dir", "weather_code", "weather_text", "updated_at",
)


def upsert_weather(rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            f"""INSERT INTO daily_weather ({", ".join(_WEATHER_COLS)})
                VALUES ({", ".join(":" + c for c in _WEATHER_COLS)})
                ON CONFLICT(city, date) DO UPDATE SET
                temp_max=excluded.temp_max, temp_min=excluded.temp_min,
                humidity_mean=excluded.humidity_mean, wind_speed_max=excluded.wind_speed_max,
                wind_dir=excluded.wind_dir, weather_code=excluded.weather_code,
                weather_text=excluded.weather_text, updated_at=excluded.updated_at""",
            rows,
        )
        return conn.total_changes


def get_weather(city: str | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
    sql = "SELECT * FROM daily_weather WHERE 1=1"
    params: list[Any] = []
    if city:
        sql += " AND city=?"
        params.append(city)
    if start:
        sql += " AND date>=?"
        params.append(start)
    if end:
        sql += " AND date<=?"
        params.append(end)
    sql += " ORDER BY date"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------- hourly_air

_HOURLY_COLS = (
    "city", "dt", "aqi", "quality", "primary_pollutant",
    "pm25", "pm10", "so2", "no2", "co", "o3", "updated_at",
)


def upsert_hourly(city: str, rows: Iterable[dict[str, Any]]) -> int:
    """写入逐小时数据（幂等 upsert）。"""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            f"""INSERT INTO hourly_air ({", ".join(_HOURLY_COLS)})
                VALUES ({", ".join(":" + c for c in _HOURLY_COLS)})
                ON CONFLICT(city, dt) DO UPDATE SET
                  aqi=excluded.aqi, quality=excluded.quality,
                  primary_pollutant=excluded.primary_pollutant,
                  pm25=excluded.pm25, pm10=excluded.pm10, so2=excluded.so2,
                  no2=excluded.no2, co=excluded.co, o3=excluded.o3,
                  updated_at=excluded.updated_at""",
            [{
                "city": city,
                "dt": r["dt"],
                "aqi": r.get("aqi"),
                "quality": r.get("quality"),
                "primary_pollutant": r.get("primary"),
                "pm25": r.get("pm25"),
                "pm10": r.get("pm10"),
                "so2": r.get("so2"),
                "no2": r.get("no2"),
                "co": r.get("co"),
                "o3": r.get("o3"),
                "updated_at": r.get("updated_at"),
            } for r in rows],
        )
        return conn.total_changes


def get_hourly(city: str | None = None, start: str | None = None, end: str | None = None) -> list[dict]:
    sql = "SELECT * FROM hourly_air WHERE 1=1"
    params: list[Any] = []
    if city:
        sql += " AND city=?"
        params.append(city)
    if start:
        sql += " AND dt>=?"
        params.append(start)
    if end:
        sql += " AND dt<=?"
        params.append(end)
    sql += " ORDER BY dt"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------- job_runs

def log_job(job: str, started_at: str, finished_at: str, status: str, message: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO job_runs (job, started_at, finished_at, status, message) "
            "VALUES (?, ?, ?, ?, ?)",
            (job, started_at, finished_at, status, message),
        )
        return cur.lastrowid


def get_job_runs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]

"""采集编排：启动回填、每日任务、升级扫描、实时快照、天气回填。

数据来源优先级：真气网官方数据（aqistudy）→ 失败时 Open-Meteo 模型补采。
每一步独立 try/except，失败只记 job_runs 与日志，不中断其他任务。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import config
import cn_aqi
from collector import aqistudy_client, bjmemc_client, cnemc_client, openmeteo_client
from database import repo

logger = logging.getLogger("backfill")


def _now_iso() -> str:
    return datetime.now(config.TZ).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(config.TZ).date().isoformat()


def _yesterday() -> str:
    return (datetime.now(config.TZ).date() - timedelta(days=1)).isoformat()


def _job(name: str, fn):
    """任务包装：记录 job_runs，异常不向上抛。"""
    started = _now_iso()
    try:
        msg = fn()
        repo.log_job(name, started, _now_iso(), "ok", msg)
        logger.info("[%s] 完成: %s", name, msg)
        return msg
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}"
        repo.log_job(name, started, _now_iso(), "fail", msg)
        logger.exception("[%s] 失败: %s", name, msg)
        return None


# ---------------------------------------------------------------- 行构建

def _row_from_aqistudy(city: str, item: dict, updated_at: str) -> dict:
    """真气网日行 → daily_air 行（补算 aqi_calc/等级/首要污染物做校验）。"""
    def r1(v):
        return round(v, 1) if isinstance(v, (int, float)) else None

    pm25, pm10, so2, no2, co, o3_8h = (
        r1(item.get(k)) for k in ("pm25", "pm10", "so2", "no2", "co", "o3_8h")
    )
    aqi = item.get("aqi")
    aqi_calc, level, primary = cn_aqi.aqi_from_components(pm25, pm10, so2, no2, co, o3_8h)
    if aqi is not None and aqi_calc is not None and abs(aqi - aqi_calc) > 2:
        logger.warning("%s %s 官方 AQI=%s 与按浓度复算 %s 差异较大",
                       city, item["date"], aqi, aqi_calc)
    return {
        "city": city, "date": item["date"],
        "aqi": aqi if aqi is not None else aqi_calc,
        "aqi_calc": aqi_calc,
        "pm25": pm25, "pm10": pm10, "so2": so2, "no2": no2, "co": co,
        "o3_8h": o3_8h, "o3_8h_check": None,
        "source": "aqistudy", "quality_level": level,
        "primary_pollutant": primary, "updated_at": updated_at,
    }


def _row_from_openmeteo(city: str, date: str, means: dict,
                        o3_mda8: float | None, updated_at: str) -> dict:
    """Open-Meteo 聚合日行 → daily_air 行（AQI 由浓度按国标复算）。"""
    pm25, pm10, so2, no2, co = (
        means.get(k) for k in ("pm25", "pm10", "so2", "no2", "co_mgm3")
    )
    aqi, level, primary = cn_aqi.aqi_from_components(pm25, pm10, so2, no2, co, o3_mda8)
    return {
        "city": city, "date": date,
        "aqi": aqi, "aqi_calc": aqi,
        "pm25": pm25, "pm10": pm10, "so2": so2, "no2": no2, "co": co,
        "o3_8h": o3_mda8, "o3_8h_check": o3_mda8,
        "source": "open-meteo", "quality_level": level,
        "primary_pollutant": primary, "updated_at": updated_at,
    }


# ---------------------------------------------------------------- 采集链路

def run_backfill():
    """启动回填（幂等，重启安全）：2026-09-01 → 昨日。"""
    def _run() -> str:
        end = _yesterday()
        updated = _now_iso()
        n_official = n_model = 0

        for c in config.CITIES:
            city, lat, lon = c["name"], c["lat"], c["lon"]

            # 1. 官方整段拉取（1 次调用拿整段，效率优先）
            try:
                items = aqistudy_client.fetch_daily(city, config.BACKFILL_START, end)
                repo.upsert_daily([_row_from_aqistudy(city, it, updated) for it in items])
                n_official += len(items)
                logger.info("%s 官方整段拉取 %d 行", city, len(items))
            except Exception as e:  # noqa: BLE001
                logger.warning("%s 官方整段拉取失败: %s", city, e)

            # 2. 缺失日期逐日重试（先单日探测：整段失败且单日也失败 → 源整体故障，跳过逐日）
            missing = repo.get_missing_dates(city, config.BACKFILL_START, end, "aqistudy")
            if missing:
                probe_ok = False
                try:
                    aqistudy_client.fetch_day(city, config.BACKFILL_START,
                                              attempts=1, delays=(0.0,))
                    probe_ok = True
                except Exception as e:  # noqa: BLE001
                    logger.warning("%s 官方源探测失败，跳过逐日重试: %s", city, e)
                if probe_ok:
                    for d in missing:
                        try:
                            items = aqistudy_client.fetch_day(city, d)
                            if items:
                                repo.upsert_daily([_row_from_aqistudy(city, items[0], updated)])
                                n_official += 1
                        except Exception as e:  # noqa: BLE001
                            logger.warning("%s %s 逐日重试失败: %s", city, d, e)

            # 3. Open-Meteo：MDA8 交叉验证（全日期回写）+ 模型补采（仍缺失的日期）
            still = repo.get_missing_dates(city, config.BACKFILL_START, end, "aqistudy")
            try:
                means_map, o3_map = openmeteo_client.fetch_hourly_air(lat, lon)
                repo.upsert_o3_check(
                    city, {d: o3_map.get(d) for d in means_map}, updated
                )
                rows = [
                    _row_from_openmeteo(city, d, means_map[d], o3_map.get(d), updated)
                    for d in still
                    if d in means_map
                    and means_map[d].get("valid_hours", 0) >= config.FALLBACK_MIN_HOURS
                ]
                if rows:
                    repo.upsert_daily(rows)
                    n_model += len(rows)
                    logger.info("%s 模型补采 %d 行: %s", city, len(rows),
                                [r["date"] for r in rows])
            except Exception as e:  # noqa: BLE001
                logger.warning("%s Open-Meteo 补采/交叉验证失败: %s", city, e)

        run_weather_backfill()
        _fetch_cnemc_daily()
        try:
            run_realtime()
        except Exception as e:  # noqa: BLE001
            logger.warning("实时快照失败: %s", e)
        return f"官方 {n_official} 行，模型补采 {n_model} 行"

    return _job("backfill", _run)


def run_daily():
    """每日任务（00:30）：昨日官方数据 + 模型兜底 + 交叉验证 + 天气。"""
    def _run() -> str:
        yesterday = _yesterday()
        updated = _now_iso()
        n = 0
        for c in config.CITIES:
            city, lat, lon = c["name"], c["lat"], c["lon"]
            try:
                items = aqistudy_client.fetch_day(city, yesterday)
                if items:
                    repo.upsert_daily([_row_from_aqistudy(city, items[0], updated)])
                    n += 1
                    continue
            except Exception as e:  # noqa: BLE001
                logger.warning("%s %s 官方拉取失败: %s", city, yesterday, e)
            # 模型兜底（不覆盖官方行）
            try:
                means_map, o3_map = openmeteo_client.fetch_hourly_air(lat, lon, past_days=3)
                repo.upsert_o3_check(city, {yesterday: o3_map.get(yesterday)}, updated)
                if yesterday in means_map and means_map[yesterday].get("valid_hours", 0) >= config.FALLBACK_MIN_HOURS:
                    repo.upsert_daily([
                        _row_from_openmeteo(city, yesterday, means_map[yesterday],
                                            o3_map.get(yesterday), updated)
                    ])
                    logger.info("%s %s 模型兜底", city, yesterday)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s %s 模型兜底失败: %s", city, yesterday, e)

        run_weather_backfill()
        _fetch_cnemc_daily()
        _upgrade_scan()
        return f"新增官方 {n} 行"

    return _job("daily", _run)


def _upgrade_scan() -> int:
    """近 14 天模型补采行 → 重试官方数据（官方发布延迟的兜底）。"""
    updated = _now_iso()
    n = 0
    for c in config.CITIES:
        city = c["name"]
        for d in repo.get_fallback_dates(city, config.UPGRADE_SCAN_DAYS):
            try:
                items = aqistudy_client.fetch_day(city, d)
                if items:
                    repo.upsert_daily([_row_from_aqistudy(city, items[0], updated)])
                    n += 1
                    logger.info("%s %s 已升级为官方数据", city, d)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s %s 升级重试失败: %s", city, d, e)
    return n


def run_upgrade_scan():
    """升级扫描任务（08:10）。"""
    def _run() -> str:
        return f"升级 {_upgrade_scan()} 行"

    return _job("upgrade_scan", _run)


def run_realtime():
    """实时快照（每小时）：监测总站官方平台。

    - 目标城市（北京/南京）：GetAQIDataPublishLiveInfo（含六项浓度）
    - 周边城市：GetAllCityRealTimeAQIModels（全国快照过滤，AQI/等级/首要污染物）
    """
    def _run() -> str:
        captured = _now_iso()
        snapshot = []
        target_names = {c["name"] for c in config.CITIES}
        # 目标城市实时详情（含浓度）；北京在监测总站平台不可达时由北京市监测中心兜底
        for c in config.CITIES:
            info = None
            try:
                info = cnemc_client.fetch_city_live_info(config.CNEMC_CITY_CODES[c["name"]])
            except Exception as e:  # noqa: BLE001
                logger.warning("CNEMC %s 实时详情失败: %s", c["name"], e)
            if info is None and c["name"] == "北京":
                try:
                    bj = bjmemc_client.fetch_beijing_snapshot()
                    info = {
                        "aqi": bj["aqi"], "quality": bj["quality"], "pm25": bj["pm25"],
                        "primary_pollutant": bj["primary_pollutant"],
                    }
                    logger.info("北京实时数据来自北京市生态环境监测中心（站点 %d 个）", bj["station_count"])
                except Exception as e:  # noqa: BLE001
                    logger.warning("bjmemc 北京兜底失败: %s", e)
            if info:
                snapshot.append({
                    "city": c["name"], "province": None,
                    "aqi": info["aqi"], "quality": info["quality"],
                    "pm25": info["pm25"], "primary_pollutant": info["primary_pollutant"],
                    "captured_at": captured,
                })
        # 周边城市：全国快照按名匹配
        try:
            allc = cnemc_client.fetch_all_cities_realtime()
            by_name = {r["area"].replace("市", ""): r for r in allc if r.get("area")}
            for name_cn in config.ALL_SNAPSHOT_CITIES:
                if name_cn in target_names:
                    continue
                r = by_name.get(name_cn)
                if not r:
                    continue
                snapshot.append({
                    "city": name_cn, "province": None,
                    "aqi": r["aqi"], "quality": r["quality"],
                    "pm25": None, "primary_pollutant": r["primary_pollutant"],
                    "captured_at": captured,
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("CNEMC 全国快照失败: %s", e)
        if not snapshot:
            raise ValueError("CNEMC 未匹配到任何目标城市")
        repo.replace_realtime(snapshot)
        return f"快照 {len(snapshot)} 城"

    return _job("realtime", _run)


def _fetch_cnemc_daily(end_date: str | None = None, quiet: bool = False) -> int:
    """拉取监测总站官方每日 AQI，写入 daily_air.aqi_official（不动模型浓度列）。"""
    end = end_date or _yesterday()
    n = 0
    for c in config.CITIES:
        city = c["name"]
        try:
            rows = cnemc_client.fetch_city_daily_history(config.CNEMC_CITY_CODES[city])
            rows = [r for r in rows
                    if r.get("date") and config.BACKFILL_START <= r["date"] <= end]
            if rows:
                n += repo.upsert_official_aqi(city, rows)
                logger.info("%s 官方每日 AQI %d 行", city, len(rows))
        except Exception as e:  # noqa: BLE001
            if not quiet:
                logger.warning("%s 官方每日 AQI 拉取失败: %s", city, e)
    return n


def run_collect_lean():
    """轻量采集（供 GitHub Actions 定时用）：跳过已失效的真气网，只采可用数据源。

    - Open-Meteo 模型日均浓度（幂等，补齐缺失日期）
    - 监测总站官方每日 AQI（若恢复）
    - 天气 + 实时快照
    """
    def _run() -> str:
        end = _yesterday()
        updated = _now_iso()
        n_model = 0
        for c in config.CITIES:
            city, lat, lon = c["name"], c["lat"], c["lon"]
            missing = [d for d in repo.get_missing_dates(city, config.BACKFILL_START, end, "aqistudy")
                       if not repo.get_daily(city, d, d)]
            if not missing:
                continue
            try:
                means_map, o3_map = openmeteo_client.fetch_hourly_air(lat, lon)
                repo.upsert_o3_check(city, {d: o3_map.get(d) for d in means_map}, updated)
                rows = [
                    _row_from_openmeteo(city, d, means_map[d], o3_map.get(d), updated)
                    for d in missing
                    if d in means_map and means_map[d].get("valid_hours", 0) >= config.FALLBACK_MIN_HOURS
                ]
                if rows:
                    repo.upsert_daily(rows)
                    n_model += len(rows)
            except Exception as e:  # noqa: BLE001
                logger.warning("%s 模型补采失败: %s", city, e)
        _fetch_cnemc_daily()
        run_weather_backfill()
        try:
            run_realtime()
        except Exception as e:  # noqa: BLE001
            logger.warning("实时快照失败: %s", e)
        return f"模型补采 {n_model} 行"

    return _job("collect_lean", _run)


def run_cnemc_recovery():
    """每 30 分钟探测监测总站平台；恢复后立即补采官方每日 AQI 与实时快照。

    平台未恢复时不写 job_runs，避免日志刷屏；恢复时记录一次并触发实时快照。
    """
    n = _fetch_cnemc_daily(quiet=True)
    if n > 0:
        logger.info("官方平台已恢复，补采官方 AQI %d 行", n)
        repo.log_job("cnemc_recovery", _now_iso(), _now_iso(), "ok",
                     f"官方平台已恢复，补采官方 AQI {n} 行")
        try:
            run_realtime()
        except Exception as e:  # noqa: BLE001
            logger.warning("恢复后实时快照失败: %s", e)


def run_weather_backfill():
    """天气回填/更新（两城，含未来 3 天预报）。"""
    def _run() -> str:
        updated = _now_iso()
        n = 0
        for c in config.CITIES:
            city, lat, lon = c["name"], c["lat"], c["lon"]
            rows = openmeteo_client.fetch_daily_weather(lat, lon)
            for r in rows:
                r["city"] = city
                r["updated_at"] = updated
            n += repo.upsert_weather(rows)
        return f"天气 {n} 行"

    return _job("weather", _run)

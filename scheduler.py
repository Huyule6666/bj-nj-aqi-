"""APScheduler 任务注册与手动触发。"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

import config

scheduler = BackgroundScheduler(
    timezone=config.TZ,
    executors={"default": ThreadPoolExecutor(max_workers=4)},
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
)

_MANUAL_SCOPES = {
    "all": "run_backfill",
    "daily": "run_daily",
    "realtime": "run_realtime",
    "weather": "run_weather_backfill",
}


def start() -> None:
    """注册全部任务并启动调度器（应用 lifespan 中调用一次）。"""
    if scheduler.running:
        return
    from collector import backfill

    now = datetime.now(config.TZ)
    # 启动回填：+2 秒，幂等，重启安全
    scheduler.add_job(backfill.run_backfill, "date",
                      run_date=now + timedelta(seconds=2),
                      id="startup_backfill", misfire_grace_time=60)
    # 每日 00:30：昨日数据
    scheduler.add_job(backfill.run_daily, "cron", id="daily",
                      hour=config.DAILY_CRON["hour"], minute=config.DAILY_CRON["minute"])
    # 每日 08:10：官方数据升级扫描
    scheduler.add_job(backfill.run_upgrade_scan, "cron", id="upgrade_scan",
                      hour=config.UPGRADE_CRON["hour"], minute=config.UPGRADE_CRON["minute"])
    # 每小时整点：实时快照
    scheduler.add_job(backfill.run_realtime, "cron", id="realtime",
                      hour=config.REALTIME_CRON["hour"], minute=config.REALTIME_CRON["minute"])
    # 每 30 分钟：探测官方平台是否恢复，恢复即补采
    scheduler.add_job(backfill.run_cnemc_recovery, "cron", id="cnemc_recovery",
                      minute="*/30")
    scheduler.start()


def trigger_manual(scope: str) -> None:
    """手动触发采集（/api/collect 用），1 秒后异步执行。"""
    from collector import backfill

    fn = getattr(backfill, _MANUAL_SCOPES.get(scope, ""), None)
    if fn is None:
        raise ValueError(f"未知 scope: {scope}（可选 {list(_MANUAL_SCOPES)}）")
    scheduler.add_job(
        fn, "date",
        run_date=datetime.now(config.TZ) + timedelta(seconds=1),
        id=f"manual_{scope}_{datetime.now(config.TZ).timestamp():.0f}",
        misfire_grace_time=30,
    )

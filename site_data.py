"""组装站点数据（site_data.json），本地 app 与 GitHub Actions 采集器共用。

前端只需拉取这一份 JSON，本地（FastAPI 提供 /site_data.json）和
GitHub Pages（Actions 采集后提交 data/site_data.json）都能直接渲染。
"""
from __future__ import annotations

from datetime import datetime

import config
from database import repo


def build_site_data() -> dict:
    cities = [c["name"] for c in config.CITIES]
    today = datetime.now(config.TZ).date().isoformat()

    realtime = {r["city"]: r for r in repo.get_realtime(cities)}
    rt_all = {r["city"]: r for r in repo.get_realtime(config.ALL_SNAPSHOT_CITIES)}

    latest = {
        "captured_at": repo.get_realtime_captured_at(),
        "today": today,
        "cities": {
            c: {"realtime": realtime.get(c), "latest_daily": repo.get_latest_daily(c)}
            for c in cities
        },
    }
    around = {
        "captured_at": repo.get_realtime_captured_at(),
        "groups": {
            target: [rt_all[n] for n in names if n in rt_all]
            for target, names in config.SURROUNDING.items()
        },
    }
    return {
        "generated_at": datetime.now(config.TZ).isoformat(timespec="seconds"),
        "meta": {
            "cities": cities,
            "surrounding": config.SURROUNDING,
            "range": repo.available_range(),
            "backfill_start": config.BACKFILL_START,
        },
        "daily": {c: repo.get_daily(c) for c in cities},
        "latest": latest,
        "around": around,
        "weather": {c: {"city": c, "today": today, "rows": repo.get_weather(c)} for c in cities},
        "status": {
            "job_runs": repo.get_job_runs(20),
            "counts": repo.counts_by_source(),
            "range": repo.available_range(),
            "realtime_captured_at": repo.get_realtime_captured_at(),
        },
    }

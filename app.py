"""FastAPI 应用：REST 路由 + lifespan + 静态托管。

运行：python app.py → http://127.0.0.1:8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from database import db, repo
from scheduler import scheduler, start as start_scheduler

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    db.init_db()
    start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="北京·南京空气质量监测", lifespan=lifespan)


# ---------------------------------------------------------------- 查询端点

@app.get("/site_data.json")
def site_data_json():
    """聚合站点数据（本地与 GitHub Pages 前端共用同一份）。"""
    from site_data import build_site_data

    return build_site_data()


@app.get("/api/meta")
def api_meta():
    return {
        "cities": [c["name"] for c in config.CITIES],
        "surrounding": config.SURROUNDING,
        "range": repo.available_range(),
        "backfill_start": config.BACKFILL_START,
    }


@app.get("/api/daily")
def api_daily(
    city: str | None = Query(default=None, description="城市名，如 北京"),
    start: str | None = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end: str | None = Query(default=None, description="结束日期 YYYY-MM-DD"),
):
    return {"rows": repo.get_daily(city, start, end)}


@app.get("/api/latest")
def api_latest():
    realtime = {r["city"]: r for r in repo.get_realtime([c["name"] for c in config.CITIES])}
    cities = {}
    for c in config.CITIES:
        cities[c["name"]] = {
            "realtime": realtime.get(c["name"]),
            "latest_daily": repo.get_latest_daily(c["name"]),
        }
    return {
        "captured_at": repo.get_realtime_captured_at(),
        "today": datetime.now(config.TZ).date().isoformat(),
        "cities": cities,
    }


@app.get("/api/around")
def api_around():
    rt = {r["city"]: r for r in repo.get_realtime(config.ALL_SNAPSHOT_CITIES)}
    groups = {
        target: [rt[n] for n in names if n in rt]
        for target, names in config.SURROUNDING.items()
    }
    return {"captured_at": repo.get_realtime_captured_at(), "groups": groups}


@app.get("/api/weather")
def api_weather(city: str = Query(default="北京")):
    if city not in [c["name"] for c in config.CITIES]:
        raise HTTPException(404, f"未知城市: {city}")
    return {
        "city": city,
        "today": datetime.now(config.TZ).date().isoformat(),
        "rows": repo.get_weather(city),
    }


@app.get("/api/status")
def api_status():
    return {
        "job_runs": repo.get_job_runs(20),
        "counts": repo.counts_by_source(),
        "range": repo.available_range(),
        "realtime_captured_at": repo.get_realtime_captured_at(),
    }


class CollectRequest(BaseModel):
    scope: str = "all"  # all | daily | realtime | weather


@app.post("/api/collect")
def api_collect(req: CollectRequest):
    from scheduler import trigger_manual

    try:
        trigger_manual(req.scope)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"status": "started", "scope": req.scope}


# ---------------------------------------------------------------- 静态页（须在 API 路由之后）

app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_config=None)

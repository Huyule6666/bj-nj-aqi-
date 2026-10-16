# 北京 · 南京空气质量监测

本地运行的空气质量数据自动采集与可视化网站：自 2026-09-01 起，每日自动采集北京、南京的
中国标准 AQI 与 PM2.5 / PM10 / SO₂ / NO₂ / CO 日均浓度、臭氧日最大 8 小时滑动平均（O3-8h），
并展示天气与周边城市实时数据。

## 数据来源

| 数据 | 来源 | 说明 |
|---|---|---|
| 实时浓度 / 周边城市 / 官方每日 AQI | 中国环境监测总站发布平台 [air.cnemc.cn:18007](https://air.cnemc.cn:18007/) | 国内权威官方数据 |
| 北京实时数据（兜底） | 北京市生态环境监测中心 [zx.bjmemc.com.cn](http://zx.bjmemc.com.cn/) | 总站平台不可达时自动切换；页面数据 DES 加密内嵌，解密后取 36 个站点均值 |
| 历史日均浓度（PM2.5/PM10/SO₂/NO₂/CO、O3-8h） | [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api)（CAMS 模型，免费无 key） | 官方平台不公开历史浓度，以模型数据补采并标注「模型数据」 |
| 天气 | [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | 温度/湿度/风/天气现象 |

**免责声明**：本工具仅用于个人参考。官方平台接口非公开文档、可能改版（字段名依据其前端 JS 推断）；
模型数据与官方监测值存在系统性偏差。真气网（aqistudy）接口当前改版失效，若恢复会自动升级浓度数据。

## 运行

要求 **Python 3.11 或 3.12**（py-mini-racer 的 Windows wheel 最稳；3.13+ 可能安装失败）。

```bat
cd C:\Users\王垣贺\aqi-monitor
python -m pip install -r requirements.txt
set PYTHONUTF8=1          :: 避免控制台中文乱码（日志文件本身为 UTF-8）
python app.py
```

浏览器打开 <http://127.0.0.1:8000>。启动后约 2 秒自动开始回填 2026-09-01 至今的数据，
几十秒内完成；页面可随时刷新查看。**服务仅在程序运行时采集**。

### 定时任务

| 任务 | 时间 | 说明 |
|---|---|---|
| 回填 | 启动时 | 幂等，重启安全 |
| 每日采集 | 每天 00:30 | 昨日官方数据；未发布则模型兜底 |
| 升级扫描 | 每天 08:10 | 近 14 天模型补采行重试官方数据 |
| 实时快照 | 每小时整点 | 目标 + 周边 18 城 |
| 天气 | 回填 / 每日任务内 | 历史 + 未来 3 天预报 |

### 开机自启（可选）

```bat
schtasks /create /tn "AQIMonitor" /tr "python C:\Users\王垣贺\aqi-monitor\app.py" /sc onlogon /rl limited
```

### 离线使用（可选）

页面图表依赖 Chart.js CDN（`cdn.jsdelivr.net/npm/chart.js@4.5.1`）。离线环境请下载
`chart.umd.min.js` 到 `static/vendor/`，并把 `index.html` 中的 script 地址改为
`vendor/chart.umd.min.js`。

## 排障

- **实时面板显示「—」或全部失败**：`config.py` 中的 `WAQI_TOKEN` 还是 `demo`（demo 仅返回
  上海示例数据）。到 [aqicn.org/data-platform/token](https://aqicn.org/data-platform/token/)
  用邮箱免费注册，把 token 填入 `config.py` 后重启。
- **真气网接口失效**（日志出现 空数据/解密失败）：先 `pip install -U akshare`（其加解密
  随真气网改版更新）；期间缺失日期由 Open-Meteo 模型数据兜底，恢复后升级扫描自动换回官方数据。
- **`py-mini-racer` 安装失败**：换 Python 3.11/3.12。
- **图表不显示、控制台报 CDN 错误**：网络无法访问 jsdelivr，按上文离线方案处理；数据明细表不受影响。
- **日期缺失**：查看页面底部状态栏任务记录，或用 `POST /api/collect {"scope":"all"}` 手动补采。

## 项目结构

```
app.py                  # FastAPI：REST 路由 + 调度器 + 静态托管
scheduler.py            # APScheduler 任务注册
config.py               # 城市/坐标/周边城市/回填起点等全部常量
cn_aqi.py               # HJ 633-2012 AQI 计算 + MDA8（含自测：python cn_aqi.py）
collector/              # aqistudy_client / openmeteo_client / backfill 编排
database/               # db.py（建表）+ repo.py（全部 SQL）
static/                 # 前端单页（index.html / app.js / style.css）
data/aqi.db             # SQLite（运行时生成）
logs/app.log            # 日志（运行时生成）
```

## 中国标准 AQI 说明

- 计算依据 HJ 633-2012：由各污染物日均浓度分段线性求 IAQI，AQI = max(IAQI)；
  O3 采用日最大 8 小时滑动平均（MDA8）；CO 限值单位为 mg/m³。
- 表中 `aqi` 为官方发布值，`aqi_calc` 为本库按浓度复算值（校验用），二者差 >2 时记录日志。

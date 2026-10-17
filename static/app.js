/* 北京 · 南京空气质量监测 — 前端逻辑（精简版：KPI + 明细表 + 天气） */
"use strict";

// ---------- 常量 ----------
const GB_LEVELS = [
  { max: 50, label: "优", color: "#00E400" },
  { max: 100, label: "良", color: "#FFFF00" },
  { max: 150, label: "轻度污染", color: "#FF7E00" },
  { max: 200, label: "中度污染", color: "#FF0000" },
  { max: 300, label: "重度污染", color: "#99004C" },
  { max: Infinity, label: "严重污染", color: "#7E0023" },
];

// ---------- 状态 ----------
let CITIES = [];
let dailyByCity = {};   // 城市 -> 全部日行（升序）

// ---------- 工具 ----------
const levelOf = (aqi) => (aqi == null ? null : GB_LEVELS.find((l) => aqi <= l.max));
const sourceText = (r) => (r.source === "aqistudy" ? "官方" : "模型数据");
const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const addDays = (dateStr, n) => {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() + n);
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (id) => document.getElementById(id);

// ---------- 数据加载 ----------
async function fetchJson(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${url} → HTTP ${r.status}`);
  return r.json();
}

async function loadAll() {
  try {
    const data = await fetchJson("site_data.json");
    CITIES = data.meta.cities;
    dailyByCity = data.daily || {};
    renderKpi(data.latest);
    renderWeather(data.weather);
    renderDetailsTables();
    renderStatus(data.status);
  } catch (e) {
    console.error(e);
    $("status-bar").textContent = `加载失败：${e.message}（本地请运行 python app.py）`;
  }
}

// ---------- KPI 卡 ----------
function levelChipHtml(level) {
  if (!level) return `<span class="placeholder">—</span>`;
  const color = GB_LEVELS.find((l) => l.label === level)?.color || "#898781";
  const text = level === "优" || level === "良" ? "#0b0b0b" : "#ffffff";
  return `<span class="level-chip" style="background:${color};color:${text}">${esc(level)}</span>`;
}

function renderKpi(latest) {
  const row = $("kpi-row");
  row.innerHTML = "";
  for (const city of CITIES) {
    const d = latest.cities[city] || {};
    const rt = d.realtime;
    const ld = d.latest_daily;
    const rtPart = rt
      ? `<div class="kpi-main">
           <div class="kpi-hero">${rt.aqi ?? "—"}<span class="unit">AQI</span></div>
           ${levelChipHtml(rt.quality)}
         </div>
         <div class="kpi-meta">
           <div class="row"><span>首要污染物</span><span>${esc(rt.primary_pollutant) || "无"}</span></div>
           <div class="row"><span>PM2.5</span><span>${rt.pm25 ?? "—"} µg/m³</span></div>
           <div class="row"><span>快照时间</span><span>${fmtTime(latest.captured_at)}</span></div>
         </div>`
      : `<div class="kpi-main"><span class="placeholder">实时数据采集中…（每小时整点更新）</span></div>`;
    const ldOfficial = ld && (ld.aqi_official != null || ld.source === "aqistudy");
    const ldAqi = ld ? (ld.aqi_official ?? ld.aqi) : null;
    const ldBadge = ldOfficial
      ? `<span class="source-badge official">官方</span>`
      : `<span class="source-badge model">模型数据</span>`;
    const ldPart = ld
      ? `<div class="kpi-meta" style="margin-top:10px;border-top:1px solid var(--gridline);padding-top:8px">
           <div class="row"><span>最近日数据 ${ld.date}${ldBadge}</span></div>
           <div class="row"><span>AQI / PM2.5 / O3-8h</span>
             <span>${ldAqi ?? "—"} / ${ld.pm25_official ?? ld.pm25 ?? "—"} / ${ld.o3_8h_official ?? ld.o3_8h ?? "—"}</span></div>
         </div>`
      : `<div class="kpi-meta"><span class="placeholder">日数据采集中…</span></div>`;
    row.insertAdjacentHTML("beforeend", `
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-city">${esc(city)}</span>
          <span class="kpi-time">今日实时</span>
        </div>
        ${rtPart}
        ${ldPart}
      </div>`);
  }
}

// ---------- 天气 ----------
function renderWeather(weather) {
  const row = $("weather-row");
  row.innerHTML = "";
  for (const city of CITIES) {
    const data = weather[city];
    if (!data) continue;
    const byDate = Object.fromEntries(data.rows.map((r) => [r.date, r]));
    const today = byDate[data.today];
    const tomorrow = byDate[addDays(data.today, 1)];
    const history = data.rows.filter((r) => r.date < data.today).slice(-7);
    const card = document.createElement("div");
    card.className = "weather-card";
    const dayBlock = (title, d) => d
      ? `<div><span class="muted">${title}</span>
           <div class="weather-now">
             <span class="weather-text">${esc(d.weather_text) || "—"}</span>
             <span class="weather-temp">${d.temp_max ?? "—"}℃ / ${d.temp_min ?? "—"}℃</span>
           </div>
           <div class="weather-meta">
             <span>湿度 ${d.humidity_mean ?? "—"}%</span>
             <span>风 ${esc(d.wind_dir) || "—"}${d.wind_speed_max != null ? ` ${d.wind_speed_max} m/s` : ""}</span>
           </div></div>`
      : "";
    card.innerHTML = `
      <h3>${esc(city)} 天气</h3>
      ${dayBlock("今日", today)}
      ${dayBlock("明日", tomorrow)}
      <div class="table-wrap"><table>
        <thead><tr><th>日期</th><th>天气</th><th>最高</th><th>最低</th><th>风</th></tr></thead>
        <tbody>${history.map((r) => `<tr>
          <td>${r.date.slice(5)}</td><td>${esc(r.weather_text) || "—"}</td>
          <td>${r.temp_max ?? "—"}</td><td>${r.temp_min ?? "—"}</td>
          <td>${esc(r.wind_dir) || "—"}</td>
        </tr>`).join("")}</tbody>
      </table></div>`;
    row.appendChild(card);
  }
}

// ---------- 数据明细表 ----------
function renderDetailsTables() {
  for (const city of CITIES) {
    const rows = dailyByCity[city] || [];
    const tbl = $(`table-${city}`);
    if (!tbl) continue;
    const head = `<thead><tr>
      <th>日期</th><th>AQI</th><th>等级</th><th>PM2.5</th><th>PM10</th>
      <th>SO₂</th><th>NO₂</th><th>CO</th><th>O3-8h</th>
      <th>首要污染物</th><th>来源</th></tr></thead>`;
    const f = (off, mdl) => off ?? mdl ?? "—";
    const body = rows.map((r) => {
      const aqi = r.aqi_official ?? r.aqi;
      const lv = levelOf(aqi);
      const official = r.aqi_official != null;
      return `<tr>
        <td>${r.date}</td>
        <td class="aqi-cell"><span class="level-dot" style="background:${lv ? lv.color : "#898781"}"></span>${aqi ?? "—"}</td>
        <td>${esc(r.quality_official ?? r.quality_level) || "—"}</td>
        <td>${f(r.pm25_official, r.pm25)}</td><td>${f(r.pm10_official, r.pm10)}</td>
        <td>${f(r.so2_official, r.so2)}</td><td>${f(r.no2_official, r.no2)}</td><td>${f(r.co_official, r.co)}</td>
        <td>${f(r.o3_8h_official, r.o3_8h)}</td>
        <td>${esc(r.primary_official ?? r.primary_pollutant) || "无"}</td>
        <td>${official ? "官方" : "模型"}</td>
      </tr>`;
    }).join("");
    tbl.innerHTML = head + `<tbody>${body}</tbody>`;
  }
}

// ---------- 状态栏 ----------
function renderStatus(status) {
  const bar = $("status-bar");
  const counts = status.counts || {};
  const official = counts.aqistudy || 0;
  const model = counts["open-meteo"] || 0;
  const last = (status.job_runs || [])[0];
  let jobPart = "尚无任务记录";
  if (last) {
    const cls = last.status === "ok" ? "status-ok" : "status-fail";
    jobPart = `最近任务 <b class="${cls}">${esc(last.job)}</b>：${last.status === "ok" ? "成功" : "失败"}（${fmtTime(last.started_at)}）${last.message ? ` — ${esc(last.message)}` : ""}`;
  }
  const rng = status.range || {};
  bar.innerHTML = `${jobPart} · 库内数据：${rng.min || "—"} ~ ${rng.max || "—"}，官方 ${official} 行，模型补采 ${model} 行 · 实时快照 ${fmtTime(status.realtime_captured_at)}`;
}

// ---------- 立即补采 ----------
async function collectNow() {
  const btn = $("btn-collect");
  btn.disabled = true;
  btn.textContent = "采集中…";
  const before = Date.now();
  try {
    await fetchJson("/api/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "all" }),
    });
    for (let i = 0; i < 80; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const st = await fetchJson("/api/status");
      const finished = (st.job_runs || []).find(
        (j) => new Date(j.started_at).getTime() > before - 2000 && j.finished_at
      );
      if (finished) break;
    }
  } catch (e) {
    alert(`补采失败：${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "立即补采";
    await loadAll();
  }
}

// ---------- 事件绑定 ----------
const IS_LOCAL = ["127.0.0.1", "localhost"].includes(location.hostname);
$("btn-refresh").addEventListener("click", loadAll);
if (!IS_LOCAL) {
  $("btn-collect").style.display = "none";
} else {
  $("btn-collect").addEventListener("click", collectNow);
}

// ---------- 启动 ----------
loadAll();
setInterval(loadAll, 10 * 60 * 1000);  // 每 10 分钟刷新（本地实时；Pages 随 Actions 提交更新）
if (IS_LOCAL) {
  setInterval(async () => {
    try { renderStatus(await fetchJson("/api/status")); } catch (e) { /* 忽略 */ }
  }, 60 * 1000);
}

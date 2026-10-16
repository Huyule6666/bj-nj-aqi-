/* 北京 · 南京空气质量监测 — 前端逻辑 */
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
const POLLUTANTS = [
  { key: "pm25", label: "PM2.5", slot: "--series-1" },
  { key: "pm10", label: "PM10", slot: "--series-2" },
  { key: "so2", label: "SO₂", slot: "--series-3" },
  { key: "no2", label: "NO₂", slot: "--series-4" },
  { key: "o3_8h", label: "O3-8h", slot: "--series-5" },
];
const COMPARE_METRICS = {
  aqi: { label: "AQI" },
  pm25: { label: "PM2.5 (µg/m³)" },
  pm10: { label: "PM10 (µg/m³)" },
  o3_8h: { label: "O3-8h (µg/m³)" },
};

// ---------- 状态 ----------
let CITIES = [];
let dailyByCity = {};   // 城市 -> 全部日行（升序）
let hourlyByCity = {};  // 城市 -> 逐小时行
let range = { start: null, end: null };
let charts = {};

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
    hourlyByCity = data.hourly || {};
    renderKpi(data.latest);
    renderAround(data.around);
    renderWeather(data.weather);
    renderStatus(data.status);
    renderCharts();
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

function sourceBadgeHtml(row) {
  if (!row) return "";
  return row.source === "aqistudy"
    ? `<span class="source-badge official">官方</span>`
    : `<span class="source-badge model">模型数据</span>`;
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

// ---------- 图表 ----------
function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "top",
        labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, font: { size: 11 }, color: "#52514e" },
      },
      tooltip: {
        backgroundColor: "#0b0b0b",
        titleFont: { size: 12 },
        bodyFont: { size: 12 },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { color: "#c3c2b7" },
        ticks: { maxTicksLimit: 8, maxRotation: 0, color: "#898781", font: { size: 11 } },
      },
      y: {
        beginAtZero: true,
        grid: { color: "#e1e0d9" },
        border: { display: false },
        ticks: { color: "#898781", font: { size: 11 } },
      },
    },
  };
}

function lineDs(label, data, slot, dash) {
  return {
    label,
    data,
    borderColor: `var(${slot})`,
    backgroundColor: `var(${slot})`,
    borderWidth: 2,
    borderDash: dash || [],
    pointRadius: 0,
    pointHoverRadius: 4,
    spanGaps: true,
    tension: 0,
  };
}

// AQI 等级背景带插件
const aqiBandsPlugin = {
  id: "aqiBands",
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales.y) return;
    const bands = [
      [0, 50, "#00E400"], [50, 100, "#FFFF00"], [100, 150, "#FF7E00"],
      [150, 200, "#FF0000"], [200, 300, "#99004C"], [300, 1e9, "#7E0023"],
    ];
    const yMin = scales.y.min, yMax = scales.y.max;
    ctx.save();
    for (const [lo, hi, color] of bands) {
      const y0 = Math.max(lo, yMin), y1 = Math.min(hi, yMax);
      if (y1 <= y0) continue;
      ctx.fillStyle = color + "12";
      ctx.fillRect(
        chartArea.left, scales.y.getPixelForValue(y1),
        chartArea.right - chartArea.left, scales.y.getPixelForValue(y0) - scales.y.getPixelForValue(y1)
      );
    }
    ctx.restore();
  },
};

function makeChart(id, config) {
  if (typeof Chart === "undefined") return;
  const el = $(id);
  if (!el) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el, config);
}

function filteredRows(city) {
  const rows = dailyByCity[city] || [];
  return rows.filter(
    (r) => (!range.start || r.date >= range.start) && (!range.end || r.date <= range.end)
  );
}

function yTitle(text) {
  return { display: true, text, color: "#898781", font: { size: 11 } };
}

function renderCharts() {
  Object.values(charts).forEach((c) => c.destroy());
  charts = {};
  if (typeof Chart === "undefined") {
    $("city-charts").innerHTML =
      `<div class="panel"><span class="placeholder">Chart.js CDN 加载失败，图表不可用；数据明细表仍可用。</span></div>`;
    return;
  }

  const container = $("city-charts");
  container.innerHTML = "";

  for (const city of CITIES) {
    const rows = filteredRows(city);
    const labels = rows.map((r) => r.date);
    const hasModel = rows.some((r) => r.aqi_official == null);
    const panel = document.createElement("div");
    panel.className = "chart-panel";
    panel.innerHTML = `
      <div class="panel-head">
        <h3>${esc(city)}</h3>
        ${hasModel ? `<span class="model-badge">部分日期为模型数据</span>` : ""}
      </div>
      <div class="chart-grid">
        <div><h4 class="sub-title">AQI 日均（国标等级背景）</h4>
          <div class="chart-box"><canvas id="chart-aqi-${city}"></canvas></div></div>
        <div><h4 class="sub-title">污染物日均浓度 (µg/m³)</h4>
          <div class="chart-box"><canvas id="chart-poll-${city}"></canvas></div></div>
        <div><h4 class="sub-title">CO 日均 (mg/m³)</h4>
          <div class="chart-box"><canvas id="chart-co-${city}"></canvas></div></div>
        <div><h4 class="sub-title">O3-8h：官方 vs 模型</h4>
          <div class="chart-box"><canvas id="chart-o3-${city}"></canvas></div></div>
      </div>
      <h4 class="sub-title" style="margin-top:14px">近 24 小时逐小时 AQI（监测总站官方）</h4>
      <div class="chart-box" style="height:200px"><canvas id="chart-hour-${city}"></canvas></div>`;
    container.appendChild(panel);

    if (!rows.length) continue;

    // AQI（模型 vs 官方两条线）
    const aqiOpts = baseOptions();
    aqiOpts.plugins.legend.position = "top";
    aqiOpts.plugins.tooltip.callbacks = {
      label: (ctx) => {
        const lv = levelOf(ctx.parsed.y);
        return `${ctx.dataset.label} ${ctx.parsed.y ?? "—"}（${lv ? lv.label : "—"}）`;
      },
    };
    aqiOpts.scales.y.suggestedMax = 300;
    aqiOpts.scales.y.title = yTitle("AQI");
    makeChart(`chart-aqi-${city}`, {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDs("模型 AQI", rows.map((r) => r.aqi), "--series-1"),
          lineDs("官方 AQI", rows.map((r) => r.aqi_official ?? null), "--series-6", [5, 4]),
        ],
      },
      options: aqiOpts,
      plugins: [aqiBandsPlugin],
    });

    // 污染物五系列（官方值优先，缺失日用模型补）
    const pollOpts = baseOptions();
    pollOpts.plugins.tooltip.callbacks = {
      label: (ctx) => {
        const r = rows[ctx.dataIndex];
        const src = r[ctx.dataset.pollKey + "_official"] != null ? "官方" : "模型";
        return `${ctx.dataset.label} ${ctx.parsed.y ?? "—"} µg/m³（${src}）`;
      },
    };
    pollOpts.scales.y.title = yTitle("µg/m³");
    makeChart(`chart-poll-${city}`, {
      type: "line",
      data: {
        labels,
        datasets: POLLUTANTS.map((p) => ({
          ...lineDs(p.label, rows.map((r) => r[p.key + "_official"] ?? r[p.key]), p.slot),
          pollKey: p.key,
        })),
      },
      options: pollOpts,
    });

    // CO 单系列（官方优先）
    const coOpts = baseOptions();
    coOpts.plugins.legend.display = false;
    coOpts.plugins.tooltip.callbacks = {
      label: (ctx) => {
        const r = rows[ctx.dataIndex];
        const src = r.co_official != null ? "官方" : "模型";
        return `CO ${ctx.parsed.y ?? "—"} mg/m³（${src}）`;
      },
    };
    coOpts.scales.y.title = yTitle("mg/m³");
    makeChart(`chart-co-${city}`, {
      type: "line",
      data: {
        labels,
        datasets: [lineDs("CO", rows.map((r) => r.co_official ?? r.co), "--series-2")],
      },
      options: coOpts,
    });

    // O3-8h 官方 vs 模型
    const o3Opts = baseOptions();
    o3Opts.plugins.tooltip.callbacks = {
      label: (ctx) => `${ctx.dataset.label} ${ctx.parsed.y ?? "—"} µg/m³`,
    };
    o3Opts.scales.y.title = yTitle("µg/m³");
    makeChart(`chart-o3-${city}`, {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDs("官方", rows.map((r) => r.o3_8h_official ?? null), "--series-5"),
          lineDs("模型", rows.map((r) => r.o3_8h), "--series-6", [5, 4]),
        ],
      },
      options: o3Opts,
    });

    // 近 24 小时逐小时 AQI
    const hrows = hourlyByCity[city] || [];
    if (hrows.length) {
      const hOpts = baseOptions();
      hOpts.plugins.legend.display = false;
      hOpts.plugins.tooltip.callbacks = {
        label: (ctx) => {
          const r = hrows[ctx.dataIndex];
          const lv = levelOf(r.aqi);
          return `AQI ${r.aqi}（${lv ? lv.label : "—"}）· PM2.5 ${r.pm25 ?? "—"} · PM10 ${r.pm10 ?? "—"}`;
        },
      };
      hOpts.scales.y.suggestedMax = 300;
      hOpts.scales.y.title = yTitle("AQI");
      makeChart(`chart-hour-${city}`, {
        type: "line",
        data: {
          labels: hrows.map((r) => r.dt.slice(5)),
          datasets: [lineDs("AQI", hrows.map((r) => r.aqi), "--series-1")],
        },
        options: hOpts,
        plugins: [aqiBandsPlugin],
      });
    }
  }

  renderCompareChart();
  renderDetailsTables();
}

function renderCompareChart() {
  const metric = $("compare-metric").value;
  const opts = baseOptions();
  opts.plugins.legend.position = "top";
  opts.plugins.tooltip.callbacks = {
    label: (ctx) => `${ctx.dataset.label} ${ctx.parsed.y ?? "—"}`,
  };
  opts.scales.y.title = yTitle(COMPARE_METRICS[metric].label);
  // 按日期并集对齐，避免两城数据日期不一致时错位（官方值优先）
  const byDate = {};
  for (const c of CITIES) {
    byDate[c] = Object.fromEntries(
      filteredRows(c).map((r) => [r.date, r[metric + "_official"] ?? r[metric]])
    );
  }
  const labels = [...new Set(CITIES.flatMap((c) => Object.keys(byDate[c])))].sort();
  makeChart("chart-compare", {
    type: "line",
    data: {
      labels,
      datasets: CITIES.map((c, i) =>
        lineDs(c, labels.map((d) => byDate[c][d] ?? null), `--series-${i + 1}`)
      ),
    },
    options: opts,
  });
}

// ---------- 周边城市 ----------
function renderAround(data) {
  $("around-time").textContent = data.captured_at ? `快照 ${fmtTime(data.captured_at)}（每小时更新）` : "暂无快照";
  const groups = $("around-groups");
  groups.innerHTML = "";
  for (const [target, cities] of Object.entries(data.groups || {})) {
    if (!cities.length) continue;
    const div = document.createElement("div");
    div.className = "around-group";
    const rows = cities
      .map((r) => {
        const lv = levelOf(r.aqi);
        return `<tr>
          <td>${esc(r.city)}</td>
          <td class="aqi-cell"><span class="level-dot" style="background:${lv ? lv.color : "#898781"}"></span>${r.aqi ?? "—"}</td>
          <td>${esc(r.quality) || "—"}</td>
          <td>${esc(r.primary_pollutant) || "无"}</td>
        </tr>`;
      })
      .join("");
    div.innerHTML = `
      <h3>${target === "北京" ? "京津冀" : "长三角"}</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>城市</th><th>AQI</th><th>等级</th><th>首要污染物</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
    groups.appendChild(div);
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
    const rows = filteredRows(city);
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

// ---------- 筛选 ----------
function setRange(start, end, presetBtn) {
  range = { start, end };
  $("date-start").value = start || "";
  $("date-end").value = end || "";
  document.querySelectorAll("#presets button").forEach((b) =>
    b.classList.toggle("selected", b === presetBtn)
  );
  const n = CITIES.length ? filteredRows(CITIES[0]).length : 0;
  const modelN = CITIES.length
    ? filteredRows(CITIES[0]).filter((r) => r.source === "open-meteo").length : 0;
  $("filter-note").textContent = n ? `当前显示 ${n} 天${modelN ? `（含 ${modelN} 天模型补采）` : ""}` : "当前范围无数据";
  renderCharts();
}

function applyCustomRange() {
  const s = $("date-start").value, e = $("date-end").value;
  if (s && e && s > e) { alert("起始日期不能晚于结束日期"); return; }
  setRange(s || null, e || null, null);
}

// ---------- 立即补采 ----------
async function collectNow() {
  const btn = $("btn-collect");
  btn.disabled = true;
  const before = Date.now();
  try {
    await fetchJson("/api/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "all" }),
    });
    // 轮询任务完成
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
document.querySelectorAll("#presets button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const days = parseInt(btn.dataset.days, 10);
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (days - 1));
    const p = (x) => String(x).padStart(2, "0");
    const f = (d) => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    setRange(days ? f(start) : null, days ? f(end) : null, btn);
  });
});
$("date-start").addEventListener("change", applyCustomRange);
$("date-end").addEventListener("change", applyCustomRange);
$("compare-metric").addEventListener("change", renderCompareChart);
$("btn-refresh").addEventListener("click", loadAll);
if (!IS_LOCAL) {
  // 静态部署（GitHub Pages）无后端，隐藏手动补采按钮
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

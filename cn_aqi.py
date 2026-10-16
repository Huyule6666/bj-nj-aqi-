"""中国标准 AQI（HJ 633-2012）计算与 O3 日最大 8 小时滑动平均（MDA8）。

纯函数模块，无网络依赖。运行 `python cn_aqi.py` 执行自测。
"""
from __future__ import annotations

# ---- HJ 633-2012 浓度限值表 ----
# 行：IAQI 节点；列：PM2.5/PM10/SO2/NO2 为 24h 均值 µg/m³，CO 为 24h 均值 mg/m³，
# O3-8h 为日最大 8 小时滑动平均 µg/m³。
BREAKPOINTS = {
    "pm25": [(0, 0), (50, 35), (100, 75), (150, 115), (200, 150), (300, 250), (400, 350), (500, 500)],
    "pm10": [(0, 0), (50, 50), (100, 150), (150, 250), (200, 350), (300, 420), (400, 500), (500, 600)],
    "so2":  [(0, 0), (50, 50), (100, 150), (150, 475), (200, 800), (300, 1600), (400, 2100), (500, 2620)],
    "no2":  [(0, 0), (50, 40), (100, 80), (150, 180), (200, 280), (300, 565), (400, 750), (500, 940)],
    "co":   [(0, 0), (50, 2), (100, 4), (150, 14), (200, 24), (300, 36), (400, 48), (500, 60)],
    # O3-8h 国标表只到 IAQI 300（800 µg/m³）；>800 时按末段斜率线性外推并封顶 500。
    # 现实中北京/南京达不到该量级，仅为健壮性兜底。
    "o3_8h": [(0, 0), (50, 100), (100, 160), (150, 215), (200, 265), (300, 800)],
}

# 污染物中文名（用于首要污染物显示）
POLLUTANT_NAMES = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "so2": "SO2",
    "no2": "NO2",
    "co": "CO",
    "o3_8h": "O3-8h",
}

QUALITY_LEVELS = [
    (0, "优"),
    (51, "良"),
    (101, "轻度污染"),
    (151, "中度污染"),
    (201, "重度污染"),
    (301, "严重污染"),
]

# 国标 AQI 等级颜色（前端也使用，保持单一来源）
LEVEL_COLORS = {
    "优": "#00E400",
    "良": "#FFFF00",
    "轻度污染": "#FF7E00",
    "中度污染": "#FF0000",
    "重度污染": "#99004C",
    "严重污染": "#7E0023",
}


def _round_aqi(x: float) -> int:
    """四舍五入取整。注意：不能用内置 round()（banker's rounding，62.5 会得到 62）。"""
    return int(x + 0.5)


def iaqi(pollutant: str, value: float | None) -> int | None:
    """单个污染物的空气质量分指数 IAQI。value 为 None（缺测）时返回 None。

    co 的输入单位必须为 mg/m³。
    """
    if value is None:
        return None
    table = BREAKPOINTS[pollutant]
    # 低于最低限值
    if value <= table[0][1]:
        return 0
    # O3-8h 外推分支：超过国标表最大浓度（800 µg/m³）
    if value > table[-1][1]:
        iaqi_lo, bp_lo = table[-2]
        iaqi_hi, bp_hi = table[-1]
        raw = iaqi_hi + (value - bp_hi) * (500 - iaqi_hi) / (bp_hi - bp_lo)
        return min(_round_aqi(raw), 500)
    # 分段线性：IAQI = (IAQI_hi-IAQI_lo)/(BP_hi-BP_lo) × (C-BP_lo) + IAQI_lo
    for (iaqi_lo, bp_lo), (iaqi_hi, bp_hi) in zip(table, table[1:]):
        if bp_lo < value <= bp_hi:
            raw = (iaqi_hi - iaqi_lo) / (bp_hi - bp_lo) * (value - bp_lo) + iaqi_lo
            return _round_aqi(raw)
    # 恰好等于最大限值（已被 <= 覆盖到末段），理论到不了这里
    return _round_aqi(table[-1][0])


def quality_level(aqi: int | None) -> str | None:
    """AQI → 空气质量等级。"""
    if aqi is None:
        return None
    for threshold, level in reversed(QUALITY_LEVELS):
        if aqi >= threshold:
            return level
    return QUALITY_LEVELS[0][1]


def level_color(level: str | None) -> str:
    return LEVEL_COLORS.get(level, "#898781")


def aqi_from_components(
    pm25: float | None = None,
    pm10: float | None = None,
    so2: float | None = None,
    no2: float | None = None,
    co_mgm3: float | None = None,
    o3_8h: float | None = None,
) -> tuple[int | None, str | None, str | None]:
    """由污染物浓度计算中国标准 AQI。

    返回 (aqi, 质量等级, 首要污染物)。
    - 所有污染物缺测 → (None, None, None)
    - AQI ≤ 50 时首要污染物为 None；>50 时取 IAQI 等于 AQI 的污染物（可并列，顿号连接）
    """
    iaqi_map = {
        "pm25": iaqi("pm25", pm25),
        "pm10": iaqi("pm10", pm10),
        "so2": iaqi("so2", so2),
        "no2": iaqi("no2", no2),
        "co": iaqi("co", co_mgm3),
        "o3_8h": iaqi("o3_8h", o3_8h),
    }
    valid = {k: v for k, v in iaqi_map.items() if v is not None}
    if not valid:
        return None, None, None
    aqi = max(valid.values())
    level = quality_level(aqi)
    if aqi <= 50:
        primary = None
    else:
        primary = "、".join(POLLUTANT_NAMES[k] for k, v in valid.items() if v == aqi)
    return aqi, level, primary


def co_ugm3_to_mgm3(v: float | None) -> float | None:
    """CO µg/m³ → mg/m³（Open-Meteo 路径用，国标 CO 限值单位为 mg/m³）。"""
    return None if v is None else v / 1000.0


def mda8(vals: list[float | None]) -> float | None:
    """O3 日最大 8 小时滑动平均（MDA8）。

    vals: 从当日 00:00 起的连续整点小时值（本地时间）。
    8h 窗口从每个整点起算（当日 24 个窗口，起点 0–23 时）；
    跨午夜窗口需要次日 0–7 时数据，故理想输入为 32 个值（当日 24 + 次日 8），
    不足时缺失窗口自动跳过。窗口内有效值 ≥ 6/8 才参与；所有窗口无效返回 None。
    """
    means = []
    for h in range(min(24, len(vals))):
        window = vals[h : h + 8]
        valid = [v for v in window if v is not None]
        if len(valid) >= 6:
            means.append(sum(valid) / len(valid))
    return max(means) if means else None


if __name__ == "__main__":
    # ---- 自测：运行 `python cn_aqi.py` 应全部通过 ----
    assert iaqi("pm25", 75) == 100, iaqi("pm25", 75)
    assert iaqi("pm25", 35) == 50
    assert iaqi("co", 2.0) == 50
    assert iaqi("o3_8h", 160) == 100

    # 综合算例：pm25=75(100) pm10=120(85) so2=30(30) no2=50(63) co=1.5(38) o3=180(118)
    aqi, level, primary = aqi_from_components(75, 120, 30, 50, 1.5, 180)
    assert aqi == 118, aqi
    assert level == "轻度污染"
    assert primary == "O3-8h", primary

    # 四舍五入：62.5 → 63（内置 round 会给 62，这是陷阱）
    assert iaqi("no2", 50) == 63, iaqi("no2", 50)
    assert _round_aqi(62.5) == 63

    # 等级边界
    assert quality_level(50) == "优"
    assert quality_level(51) == "良"
    assert quality_level(300) == "重度污染"
    assert quality_level(301) == "严重污染"

    # AQI ≤ 50 无首要污染物；>50 取并列最大值
    # pm25=20→29 pm10=30→30 so2=10→10 no2=20→25 co=0.5→13 o3=60→30，最大 30
    aqi2, _, p2 = aqi_from_components(20, 30, 10, 20, 0.5, 60)
    assert aqi2 == 30 and p2 is None
    aqi3, _, p3 = aqi_from_components(75, 150, 10, 20, 0.5, 60)  # pm25 IAQI=100, pm10 IAQI=100
    assert aqi3 == 100 and p3 == "PM2.5、PM10", p3

    # 缺测处理
    assert aqi_from_components() == (None, None, None)
    assert iaqi("pm25", None) is None

    # O3-8h 外推封顶（>800 µg/m³）
    assert iaqi("o3_8h", 900) > 300
    assert iaqi("o3_8h", 999999) == 500

    # CO 单位换算
    assert co_ugm3_to_mgm3(900) == 0.9
    assert co_ugm3_to_mgm3(None) is None

    # MDA8：恒定 100 → 100；尖峰应使结果 > 100
    assert mda8([100.0] * 32) == 100.0
    spike = [100.0] * 32
    spike[15] = 200.0
    assert 100.0 < mda8(spike) < 200.0
    # 只有当日 24 个值（无次日数据）：最后 7 个窗口跳过，仍能算出
    assert mda8([100.0] * 24) == 100.0
    # 有效值不足（全 None）
    assert mda8([None] * 32) is None
    # 窗口内有效值 < 6 不参与：仅 5 个有效值 → 无有效窗口
    almost_empty = [None] * 32
    for i in range(5):
        almost_empty[i] = 100.0
    assert mda8(almost_empty) is None

    print("cn_aqi.py 自测全部通过 ✓")

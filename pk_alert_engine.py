#!/usr/bin/env python3
"""
PK-Aware Medication Alert Engine
Incorporates drug half-life, accumulation, and lag into dosing recommendations.

Key PK principles:
  - Dose INCREASE: needs 1-2 day pre-loading (drug takes 2-3 days to reach steady state)
  - Dose DECREASE: safe, has 2-3 day residual buffer from drug carryover
  - Alert logic: forecast-based, not current-temperature-based
"""

import csv
import math
from datetime import date, timedelta

# ============================================================
# PK Parameters (Sacubitril/Valsartan - Entresto/诺欣妥)
# ============================================================
T_HALF = 11.5          # LBQ657 active metabolite half-life (hours)
DAILY_RETENTION = math.exp(-24 * math.log(2) / T_HALF)  # ≈ 0.235

# Steady state accumulation factor for daily dosing:
#   accumulation = 1 / (1 - e^(-k*tau)) = 1 / (1 - 0.235) ≈ 1.31
#   trough = accumulation * dose * DAILY_RETENTION
#   peak   = accumulation * dose
ACCUMULATION = 1.0 / (1.0 - DAILY_RETENTION)  # ≈ 1.31

def steady_state_level(dose):
    """Steady state trough level for a given daily dose (0, 0.5, 1.0)."""
    return dose * ACCUMULATION * DAILY_RETENTION

def days_to_steady_state(current_level, target_level, dose):
    """Estimate days to reach target steady state given current level."""
    if dose == 0:
        # Elimination: level * retention^days → wait until below threshold
        days = 0
        level = current_level
        while level > target_level and days < 10:
            level *= DAILY_RETENTION
            days += 1
        return max(1, days)
    else:
        # Accumulation toward new steady state
        ss_level = steady_state_level(dose)
        days = 0
        level = current_level
        while abs(level - ss_level) / ss_level > 0.05 and days < 10:
            level = level * DAILY_RETENTION + dose
            days += 1
        return max(1, days)


# ============================================================
# Forecast & Dosing Engine
# ============================================================
def compute_3d_avg_temps(history_temps, forecast):
    """
    history_temps: list of (date_str, t_max) for recent actual days
    forecast: list of (date_str, t_max, t_min, weather) for future days
    Returns: dict {date_str: t_3d_avg}
    """
    all_temps = {}
    for d, t in history_temps:
        all_temps[date.fromisoformat(d)] = t
    for f in forecast:
        all_temps[date.fromisoformat(f[0])] = f[1]

    result = {}
    all_dates = sorted(all_temps.keys())
    for i, d in enumerate(all_dates):
        if i >= 2:
            result[d.isoformat()] = round(sum(all_temps[all_dates[j]] for j in range(i-2, i+1)) / 3, 1)
    return result


def pk_aware_dose_recommendation(current_dose, current_drug_level, forecast_3d, forecast_raw):
    """
    PK-informed dosing for each forecast day.

    current_dose: 0, 0.5, or 1.0
    current_drug_level: simulated trough level before today's dose
    forecast_3d: dict {date_str: t_3d_avg}
    forecast_raw: list of (date_str, t_max, t_min, weather)

    Returns: list of dicts with per-day recommendations
    """
    recommendations = []
    dose = current_dose
    level = current_drug_level

    # Determine if cold front is approaching (T3d dropping below 15°C within 2-3 days)
    forecast_items = sorted(forecast_3d.items())
    cold_coming_in_days = None
    for i, (dt_str, t3d) in enumerate(forecast_items):
        if t3d < 15:
            cold_coming_in_days = i
            break

    warming_trend = False
    if len(forecast_items) >= 3:
        first_t3d = forecast_items[0][1]
        later_t3d = forecast_items[-1][1]
        if first_t3d >= 20 and later_t3d >= 25:
            warming_trend = True

    # Hysteresis helpers: prevent ping-pong dose changes
    def sustained_warm(start_idx, days=3):
        """Check if T3d stays ≥ 25°C for `days` consecutive days from start_idx."""
        items = list(enumerate(forecast_items))
        count = 0
        for j, (_, t3d) in items[start_idx:]:
            if t3d >= 25:
                count += 1
            else:
                break
        return count >= days

    def will_drop_below(start_idx, threshold=20, within_days=3):
        """Check if T3d drops below threshold within next N days."""
        items = list(enumerate(forecast_items))
        for j, (_, t3d) in items[start_idx:start_idx + within_days + 1]:
            if t3d < threshold:
                return True
        return False

    for i, fcast in enumerate(forecast_raw):
        dt_str, t_max, t_min, weather = fcast
        t3d = forecast_3d.get(dt_str, t_max)

        # --- PK-aware decision rules ---

        # Rule 1: Cold front approaching within 2-3 days → pre-load NOW
        if cold_coming_in_days is not None and i <= cold_coming_in_days and cold_coming_in_days <= i + 2:
            if dose < 1.0:
                rec_dose = 1.0
                reason = f"⚠️ 寒潮预警: {cold_coming_in_days-i+1}天后T3d降至15°C以下，提前加药达稳态"
                preload = True
            else:
                rec_dose = 1.0
                reason = "已全量，维持，PK保护已到位"
                preload = False

        # Rule 2: Currently in cold period → maintain 1 pill
        elif t3d < 15:
            rec_dose = 1.0
            reason = "低温维持期，保持1颗"
            preload = False

        # Rule 3: Transition season (15-25°C) → maintain current, use hysteresis
        elif 15 <= t3d < 25:
            if dose == 1.0 and warming_trend:
                rec_dose = 0.5
                reason = "气温回暖趋势，减至半颗（PK残留保护安全）"
                preload = False
            elif dose == 1.0:
                rec_dose = 1.0
                reason = "过渡期，维持1颗观察趋势"
                preload = False
            elif dose == 0.5:
                rec_dose = 0.5
                reason = "过渡期，维持半颗"
                preload = False
            elif dose == 0.0 and t3d < 20:
                # Restart threshold: only restart if T3d drops below 20°C (hysteresis)
                rec_dose = 0.5
                reason = "温度明显下降(T3d<20°C)，恢复半颗"
                preload = False
            else:
                # Currently off, T3d 20-25°C: hold (don't restart yet)
                rec_dose = 0.0
                reason = "温度可接受，维持停药观察"
                preload = False

        # Rule 4: Warm period (T3d ≥ 25°C) → consider stopping
        elif t3d >= 25:
            if dose == 1.0:
                # Step down gradually
                if sustained_warm(i, 3):
                    rec_dose = 0.5
                    reason = "持续高温，从1颗减至半颗过渡（避免骤停）"
                else:
                    rec_dose = 1.0
                    reason = "高温但不持续，维持1颗观察"
                preload = False
            elif dose == 0.5:
                # Only stop if warm is sustained AND no cold dip ahead
                if sustained_warm(i, 3) and not will_drop_below(i, 20, 3):
                    rec_dose = 0.0
                    reason = "持续高温且无降温预报，可直接停药（PK残留保护2-3天）"
                elif not sustained_warm(i, 3):
                    rec_dose = 0.5
                    reason = "高温但不持续，维持半颗等待确认"
                else:
                    rec_dose = 0.5
                    reason = "高温但预报有降温，暂维持半颗"
                preload = False
            else:
                rec_dose = 0.0
                reason = "高温期，维持停药"
                preload = False

        else:
            rec_dose = dose
            reason = "维持当前剂量"
            preload = False

        # --- Alert determination ---
        # Day-over-day max temp drop
        prev_t_max = forecast_raw[i-1][1] if i > 0 else t_max
        drop = prev_t_max - t_max

        alert_level = "无"
        alert_marker = ""
        alert_details = []

        if drop >= 5:
            alert_details.append(f"24h降温{drop}°C")
            if alert_level != "红色":
                alert_level = "黄色"
        if t_max < 10:
            alert_level = "橙色"
            alert_details.append("最高温<10°C")
        if t_max < 5 and t_min < 0:
            alert_level = "红色"
            alert_details.append("极寒")

        if alert_level == "红色":
            alert_marker = "🔴"
        elif alert_level == "橙色":
            alert_marker = "🟠"
        elif alert_level == "黄色":
            alert_marker = "🟡"

        # Project drug level after taking recommended dose
        next_level = level * DAILY_RETENTION + rec_dose

        dose_label = {0: '停药', 0.5: '半颗', 1.0: '1颗'}[rec_dose]

        recommendations.append({
            'date': dt_str,
            't_max': t_max,
            't_min': t_min,
            'weather': weather,
            't3d': t3d,
            'dose': rec_dose,
            'dose_label': dose_label,
            'drug_level': round(next_level, 3),
            'alert_level': alert_level,
            'alert_marker': alert_marker,
            'alert_details': alert_details,
            'reason': reason,
            'preload': preload,
        })

        dose = rec_dose
        level = next_level

    return recommendations


# ============================================================
# Format output for user
# ============================================================
def format_report(recommendations, current_info):
    """Generate a readable report from recommendations."""
    lines = []
    lines.append("=" * 70)
    lines.append("药代动力学(PK)修正 - 每日用药预警")
    lines.append("=" * 70)
    lines.append(f"\n当前状态: {current_info}")
    lines.append(f"\nPK参数: 半衰期={T_HALF}h, 日残留率={DAILY_RETENTION:.1%}, "
                 f"蓄积比={ACCUMULATION:.1f}, 达稳态~3天\n")

    # Check if any preload alert
    preload_days = [r for r in recommendations if r['preload']]
    non_preload = [r for r in recommendations if not r['preload']]

    if preload_days:
        lines.append("⚠️  提前加药提醒 (PK预判):")
        for r in preload_days:
            lines.append(f"  {r['date']} → {r['reason']}")

    has_alert = [r for r in recommendations if r['alert_level'] != '无']
    if has_alert:
        lines.append("\n🚨 预警:")

    lines.append(f"\n{'日期':<12} {'天气':<10} {'最高':<5} {'最低':<5} {'T3d':<7} {'推荐':<7} {'预警':<10} {'说明'}")
    lines.append("-" * 70)

    for r in recommendations:
        lines.append(f"{r['date']:<12} {r['weather']:<10} {r['t_max']}°C  {r['t_min']}°C  "
                     f"{r['t3d']}°C{'':>3} {r['dose_label']:<7} "
                     f"{r['alert_marker']}{r['alert_level']:<8} {r['reason']}")

    lines.append("-" * 70)

    # Summary
    lines.append("\n📋 PK修正总结:")
    if preload_days:
        lines.append(f"   ⚠️ 有寒潮预警 → 建议今天就开始加药，不要等温度降了再加!")
    else:
        lines.append(f"   ✓ 未来一周无寒潮，按正常节奏用药即可")

    # Dose direction awareness
    dose_changes = []
    prev = None
    for r in recommendations:
        if prev is not None and r['dose'] != prev:
            if r['dose'] > prev:
                dose_changes.append(f"  ⬆ {r['date']}: { {0:'停药',0.5:'半颗',1.0:'1颗'}[prev]}→{r['dose_label']} (加药方向: 需提前1-2天, 注意保护真空)")
            else:
                dose_changes.append(f"  ⬇ {r['date']}: { {0:'停药',0.5:'半颗',1.0:'1颗'}[prev]}→{r['dose_label']} (减药方向: PK缓冲安全)")
        prev = r['dose']

    if dose_changes:
        lines.append("\n剂量调整事件:")
        for c in dose_changes:
            lines.append(c)

    return "\n".join(lines)


# ============================================================
# Main: test with current forecast
# ============================================================
if __name__ == '__main__':
    # Load recent data to get current state
    rows = []
    with open('/Users/lichangda/Downloads/血压气温合并.csv', 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r['血压高压(收缩压)']:
                rows.append({
                    'date': date.fromisoformat(r['日期']),
                    'sys': int(r['血压高压(收缩压)']),
                    't_max': int(r['气温高温(℃)']),
                })

    recent = rows[-5:]
    t3d_recent = sum(r['t_max'] for r in recent[-3:]) / 3
    recent_bp = [r['sys'] for r in recent if r['sys']]

    # Current dose: half pill (late May)
    current_dose = 0.5
    current_level = steady_state_level(current_dose)

    # Forecast (updated 2026-05-23)
    forecast_raw = [
        ("2026-05-23", 26, 19, "中雨"),
        ("2026-05-24", 25, 18, "小雨"),
        ("2026-05-25", 24, 18, "大雨"),
        ("2026-05-26", 23, 16, "小雨转中雨"),
        ("2026-05-27", 24, 15, "小雨转多云"),
        ("2026-05-28", 25, 14, "多云"),
        ("2026-05-29", 27, 14, "多云转晴"),
    ]

    # History temps for 3d avg calculation
    history_temps = [(str(r['date']), r['t_max']) for r in rows[-3:]]

    t3d_map = compute_3d_avg_temps(history_temps, forecast_raw)
    recs = pk_aware_dose_recommendation(current_dose, current_level, t3d_map, forecast_raw)

    current_info = (f"剂量=半颗, 血药稳态水平={current_level:.2f}, "
                    f"最近T3d={t3d_recent:.1f}°C, 最近SBP={recent_bp[-1] if recent_bp else 'N/A'}")

    report = format_report(recs, current_info)
    print(report)

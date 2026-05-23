#!/usr/bin/env python3
"""
独立PK预警脚本 - 通过Clash代理获取天气，本地运行PK引擎，系统通知
用于 crontab 定时任务
"""
import csv
import json
import math
import os
import subprocess
import sys
from datetime import date, timedelta

# === PK Parameters ===
T_HALF = 11.5
DAILY_RETENTION = math.exp(-24 * math.log(2) / T_HALF)
ACCUMULATION = 1.0 / (1.0 - DAILY_RETENTION)

def steady_state_level(dose):
    return dose * ACCUMULATION * DAILY_RETENTION

# === Fetch weather forecast via Clash proxy ===
def fetch_forecast():
    """Fetch 7-day Xi'an Weiyang forecast."""
    proxy = "http://127.0.0.1:6789"
    # Try Open-Meteo API (free, no key needed)
    url = ("https://api.open-meteo.com/v1/forecast?"
           "latitude=34.26&longitude=108.94&daily=temperature_2m_max,"
           "temperature_2m_min&timezone=Asia/Shanghai&forecast_days=7")

    try:
        result = subprocess.run(
            ["curl", "-sk", "--proxy", proxy, "--connect-timeout", "10", url],
            capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            t_maxs = daily.get("temperature_2m_max", [])
            t_mins = daily.get("temperature_2m_min", [])
            forecast = []
            for i in range(len(dates)):
                forecast.append((dates[i], int(round(t_maxs[i])), int(round(t_mins[i])), ""))
            return forecast
    except Exception as e:
        print(f"Open-Meteo failed: {e}", file=sys.stderr)

    return None


# === Load recent data ===
def load_recent_data():
    rows = []
    try:
        with open('/Users/lichangda/Downloads/血压气温合并.csv', 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r['血压高压(收缩压)']:
                    rows.append({
                        'date': date.fromisoformat(r['日期']),
                        'sys': int(r['血压高压(收缩压)']),
                        't_max': int(r['气温高温(℃)']),
                    })
    except FileNotFoundError:
        pass
    return rows


# === 3-day moving avg ===
def compute_t3d(history, forecast):
    all_temps = {}
    for r in history:
        all_temps[r['date']] = r['t_max']
    for f in forecast:
        all_temps[date.fromisoformat(f[0])] = f[1]
    result = {}
    all_dates = sorted(all_temps.keys())
    for i, d in enumerate(all_dates):
        if i >= 2:
            result[d] = sum(all_temps[all_dates[j]] for j in range(i-2, i+1)) / 3
    return result


# === PK-aware recommendation ===
def pk_recommend(current_dose, current_level, forecast, t3d_map):
    recs = []
    dose = current_dose
    level = current_level

    # Check if cold coming
    cold_coming_day = None
    for i, f in enumerate(forecast):
        t3d = t3d_map.get(date.fromisoformat(f[0]), f[1])
        if t3d < 15:
            cold_coming_day = i
            break

    for i, f in enumerate(forecast):
        dt_str, t_max, t_min, _ = f
        t3d = t3d_map.get(date.fromisoformat(dt_str), t_max)

        # Decision rules (same as pk_alert_engine.py)
        if cold_coming_day is not None and cold_coming_day - i <= 2 and cold_coming_day >= i:
            rec_dose = 1.0
            reason = f"寒潮预警: {cold_coming_day-i+1}天后T3d<15°C，提前加药"
            preload = True
        elif t3d < 15:
            rec_dose = 1.0
            reason = "低温维持期，1颗"
            preload = False
        elif 15 <= t3d < 25:
            if dose == 1.0:
                rec_dose = 1.0
                reason = "过渡期，维持1颗观察"
            elif dose == 0.5:
                rec_dose = 0.5
                reason = "过渡期，维持半颗"
            else:
                rec_dose = 0.0 if t3d >= 20 else 0.5
                reason = "维持停药" if t3d >= 20 else "温度下降，恢复半颗"
            preload = False
        else:  # t3d >= 25
            if dose == 1.0:
                rec_dose = 0.5
                reason = "高温期，减至半颗过渡"
            elif dose == 0.5:
                rec_dose = 0.0
                reason = "高温期，可停药(PK缓冲安全)"
            else:
                rec_dose = 0.0
                reason = "高温期，维持停药"
            preload = False

        # Alert level
        alert_level = "无"
        alert_reason = ""
        if i > 0:
            prev_t_max = forecast[i-1][1]
            drop = prev_t_max - t_max
            if drop >= 5:
                alert_level = "黄色"
                alert_reason = f"24h降温{drop}°C"
        if t_max < 10:
            alert_level = "橙色"
            alert_reason = "最高温<10°C"
        if t_max < 5 and t_min < 0:
            alert_level = "红色"
            alert_reason = "极寒"

        new_level = level * DAILY_RETENTION + rec_dose

        recs.append({
            'date': dt_str, 't_max': t_max, 't_min': t_min,
            't3d': round(t3d, 1), 'dose': rec_dose,
            'dose_label': {0:'停药',0.5:'半颗',1.0:'1颗'}[rec_dose],
            'alert': alert_level, 'alert_reason': alert_reason,
            'reason': reason, 'preload': preload,
        })
        dose = rec_dose
        level = new_level

    return recs


def send_notification(title, body):
    script = f'display notification "{body}" with title "{title}" sound name "default"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


# === Main ===
if __name__ == '__main__':
    # Current state
    today = date.today()
    rows = load_recent_data()
    recent = rows[-5:] if len(rows) >= 5 else rows
    recent_t3d = sum(r['t_max'] for r in recent[-3:]) / 3 if len(recent) >= 3 else 25

    # Determine current dose by month + temp
    month = today.month
    if month in [12, 1, 2]:
        current_dose = 1.0
    elif month in [7, 8, 9]:
        current_dose = 0.0
    elif month in [3, 4, 10, 11]:
        current_dose = 0.5 if recent_t3d >= 15 else 1.0
    else:  # May, Jun
        current_dose = 0.5

    current_level = steady_state_level(current_dose)

    # Forecast
    forecast = fetch_forecast()
    if not forecast:
        print("ERROR: Cannot fetch forecast", file=sys.stderr)
        sys.exit(1)

    history_for_t3d = [{'date': r['date'], 't_max': r['t_max']} for r in recent[-3:]]
    t3d_map = compute_t3d(history_for_t3d, forecast)
    recs = pk_recommend(current_dose, current_level, forecast, t3d_map)

    # Build report
    lines = ["=" * 60, f"血压用药PK预警 {today}", f"当前: {current_dose}颗, T3d={recent_t3d:.1f}°C", "-" * 60]
    lines.append(f"{'日期':<12} {'高/低':<8} {'T3d':<7} {'推荐':<6} {'预警':<6} 说明")
    lines.append("-" * 60)

    has_alert = False
    for r in recs:
        a = "⚠️" if r['alert'] != '无' else ""
        lines.append(f"{r['date']:<12} {r['t_max']}/{r['t_min']:<3}°C  "
                     f"{r['t3d']}°C{'':>3} {r['dose_label']:<6} {a}{r['alert']:<5} {r['reason']}")

    lines.append("-" * 60)

    # Find alerts
    cold_alerts = [r for r in recs if r['preload']]
    other_alerts = [r for r in recs if r['alert'] != '无']

    if cold_alerts:
        has_alert = True
        lines.append(f"\n⚠️ 提前加药: {cold_alerts[0]['date']}开始，{cold_alerts[0]['reason']}")
    if other_alerts:
        has_alert = True
        for r in other_alerts:
            lines.append(f"🚨 {r['date']}: {r['alert']}预警 ({r['alert_reason']}) - {r['reason']}")

    if not has_alert:
        lines.append("✓ 未来一周无预警，维持当前剂量")

    report = "\n".join(lines)
    print(report)

    # Write to log file
    with open(os.path.expanduser("~/bp-alert-cron.log"), "a") as f:
        f.write(f"\n=== {today} ===\n")
        f.write(report + "\n")

    # Send notification if alert
    if has_alert:
        summary = " ".join([r['reason'] for r in cold_alerts + other_alerts][:3])
        send_notification("血压用药预警", summary)

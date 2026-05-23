#!/usr/bin/env python3
"""Analyze the relationship between temperature and blood pressure."""

import csv
import statistics
from collections import defaultdict
from datetime import date

# Read merged data
rows = []
with open('/Users/lichangda/Downloads/血压气温合并.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append({
            'date': r['日期'],
            'sys': int(r['血压高压(收缩压)']) if r['血压高压(收缩压)'] else None,
            'dia': int(r['血压低压(舒张压)']) if r['血压低压(舒张压)'] else None,
            't_max': int(r['气温高温(℃)']),
            't_min': int(r['气温低温(℃)']),
            'count': int(r['当天血压记录数']),
        })

# Only use days with actual BP measurements for correlation
measured = [r for r in rows if r['count'] > 0 and r['sys'] is not None]

print(f"=== 基础统计 ===")
print(f"总天数: {len(rows)}")
print(f"有实测血压天数: {len(measured)}")
print(f"平均收缩压: {statistics.mean(r['sys'] for r in measured):.1f} mmHg")
print(f"平均舒张压: {statistics.mean(r['dia'] for r in measured):.1f} mmHg")

# ---- 1. Temperature bands analysis ----
print(f"\n=== 按气温区间分析血压 ===")

def analyze_temp_bands(measured, temp_key, band_size=5):
    bands = defaultdict(list)
    for r in measured:
        t = r[temp_key]
        band = (t // band_size) * band_size
        bands[band].append(r)

    for band in sorted(bands.keys()):
        recs = bands[band]
        avg_sys = statistics.mean(r['sys'] for r in recs)
        avg_dia = statistics.mean(r['dia'] for r in recs)
        print(f"  {temp_key} {band:3d}~{band+band_size-1:3d}℃: "
              f"n={len(recs):3d}, SBP={avg_sys:.1f}, DBP={avg_dia:.1f}")

analyze_temp_bands(measured, 't_max')
print()
analyze_temp_bands(measured, 't_min')

# ---- 2. High vs Low temperature comparison ----
print(f"\n=== 高温 vs 低温对比 ===")
median_max = statistics.median(r['t_max'] for r in rows)
median_min = statistics.median(r['t_min'] for r in rows)

for temp_key, median_val in [('t_max', median_max), ('t_min', median_min)]:
    high_days = [r for r in measured if r[temp_key] >= median_val]
    low_days = [r for r in measured if r[temp_key] < median_val]

    if high_days and low_days:
        h_sys = statistics.mean(r['sys'] for r in high_days)
        h_dia = statistics.mean(r['dia'] for r in high_days)
        l_sys = statistics.mean(r['sys'] for r in low_days)
        l_dia = statistics.mean(r['dia'] for r in low_days)
        print(f"  {temp_key} >= {median_val}℃ (高温组): SBP={h_sys:.1f}, DBP={h_dia:.1f}, n={len(high_days)}")
        print(f"  {temp_key} <  {median_val}℃ (低温组): SBP={l_sys:.1f}, DBP={l_dia:.1f}, n={len(low_days)}")
        print(f"  差值 (低温-高温): SBP={l_sys-h_sys:+.1f}, DBP={l_dia-h_dia:+.1f}")
    print()

# ---- 3. Correlation coefficients ----
print(f"=== 相关性分析 (Pearson r) ===")

def pearson_r(xs, ys):
    n = len(xs)
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    sx = statistics.stdev(xs)
    sy = statistics.stdev(ys)
    return sum((x-mx)*(y-my) for x, y in zip(xs, ys)) / ((n-1) * sx * sy)

for temp_key in ['t_max', 't_min']:
    xs = [r[temp_key] for r in measured]
    for bp_key, bp_name in [('sys', '收缩压'), ('dia', '舒张压')]:
        ys = [r[bp_key] for r in measured]
        r_val = pearson_r(xs, ys)
        print(f"  {temp_key} vs {bp_name}: r = {r_val:.3f}")

# ---- 4. Extreme cold analysis ----
print(f"\n=== 极端天气条件分析 ===")

# Very cold days (min temp < 0°C)
cold_days = [r for r in measured if r['t_min'] < 0]
hot_days = [r for r in measured if r['t_max'] > 35]
moderate_days = [r for r in measured if 15 <= r['t_max'] <= 25 and r['t_min'] >= 10]

print(f"极寒天 (最低温<0℃): n={len(cold_days)}, SBP={statistics.mean(r['sys'] for r in cold_days):.1f}, "
      f"DBP={statistics.mean(r['dia'] for r in cold_days):.1f}")
print(f"酷暑天 (最高温>35℃): n={len(hot_days)}, SBP={statistics.mean(r['sys'] for r in hot_days):.1f}, "
      f"DBP={statistics.mean(r['dia'] for r in hot_days):.1f}")
print(f"舒适天 (15≤T≤25): n={len(moderate_days)}, SBP={statistics.mean(r['sys'] for r in moderate_days):.1f}, "
      f"DBP={statistics.mean(r['dia'] for r in moderate_days):.1f}")

# ---- 5. Temperature change effect ----
print(f"\n=== 气温变化对血压的影响 ===")

# Day-to-day temperature change vs BP change
changes = []
for i in range(1, len(measured)):
    prev = measured[i-1]
    curr = measured[i]
    dt_max = curr['t_max'] - prev['t_max']
    dt_min = curr['t_min'] - prev['t_min']
    dsys = curr['sys'] - prev['sys']
    ddia = curr['dia'] - prev['dia']
    changes.append({
        'dt_max': dt_max, 'dt_min': dt_min,
        'dsys': dsys, 'ddia': ddia,
    })

# When max temp drops > 5°C from previous day
big_cool = [c for c in changes if c['dt_max'] <= -5]
big_warm = [c for c in changes if c['dt_max'] >= 5]

if big_cool:
    print(f"最高温骤降 ≥5℃: n={len(big_cool)}, "
          f"ΔSBP={statistics.mean(c['dsys'] for c in big_cool):+.1f}, "
          f"ΔDBP={statistics.mean(c['ddia'] for c in big_cool):+.1f}")
if big_warm:
    print(f"最高温骤升 ≥5℃: n={len(big_warm)}, "
          f"ΔSBP={statistics.mean(c['dsys'] for c in big_warm):+.1f}, "
          f"ΔDBP={statistics.mean(c['ddia'] for c in big_warm):+.1f}")

# 10°C drop effect
for threshold in [3, 5, 8, 10]:
    cool_sharp = [c for c in changes if c['dt_max'] <= -threshold]
    if cool_sharp:
        print(f"  最高温降幅≥{threshold}℃: n={len(cool_sharp)}, "
              f"ΔSBP={statistics.mean(c['dsys'] for c in cool_sharp):+.1f}")

# ---- 6. Seasonal analysis ----
print(f"\n=== 季节差异 ===")
seasons = {'冬季(12-2月)': [12, 1, 2], '春季(3-5月)': [3, 4, 5],
           '夏季(6-8月)': [6, 7, 8], '秋季(9-11月)': [9, 10, 11]}

for season_name, months in seasons.items():
    season_data = [r for r in measured if int(r['date'].split('-')[1]) in months]
    if season_data:
        print(f"  {season_name}: n={len(season_data)}, "
              f"SBP={statistics.mean(r['sys'] for r in season_data):.1f}, "
              f"DBP={statistics.mean(r['dia'] for r in season_data):.1f}, "
              f"T_max={statistics.mean(r['t_max'] for r in season_data):.1f}℃, "
              f"T_min={statistics.mean(r['t_min'] for r in season_data):.1f}℃")

# ---- 7. Per-10°C slope for min temp ----
print(f"\n=== 每降10℃血压变化 (最低温) ===")
for bp_key, bp_name in [('sys', '收缩压'), ('dia', '舒张压')]:
    xs = [r['t_min'] for r in measured]
    ys = [r[bp_key] for r in measured]
    r_val = pearson_r(xs, ys)
    # slope = r * (std_y / std_x)
    slope = r_val * statistics.stdev(ys) / statistics.stdev(xs)
    per_10c = slope * 10
    print(f"  {bp_name}: 每降10℃ 变化 {per_10c:+.2f} mmHg, r={r_val:.3f}")

# ---- 8. Hypertension rate by temperature band ----
print(f"\n=== 不同气温下高血压比例 (SBP≥130 OR DBP≥85) ===")
for band_label, band_condition in [
    ("极寒 T_min<0℃", lambda r: r['t_min'] < 0),
    ("寒冷 0≤T_min<10℃", lambda r: 0 <= r['t_min'] < 10),
    ("凉爽 10≤T_min<20℃", lambda r: 10 <= r['t_min'] < 20),
    ("温暖 T_min≥20℃", lambda r: r['t_min'] >= 20),
]:
    band_data = [r for r in measured if band_condition(r)]
    if band_data:
        hyper = [r for r in band_data if r['sys'] >= 130 or r['dia'] >= 85]
        rate = len(hyper) / len(band_data) * 100
        print(f"  {band_label}: 高血压比例 {rate:.1f}%, "
              f"平均 SBP={statistics.mean(r['sys'] for r in band_data):.1f}, "
              f"n={len(band_data)}")

# ---- 9. Strongest BP elevation conditions ----
print(f"\n=== 血压升高最多的条件 (按收缩压排序) ===")

def describe_condition(desc, subset):
    if len(subset) < 3:
        return
    sys_avg = statistics.mean(r['sys'] for r in subset)
    dia_avg = statistics.mean(r['dia'] for r in subset)
    t_min_avg = statistics.mean(r['t_min'] for r in subset)
    t_max_avg = statistics.mean(r['t_max'] for r in subset)
    hyper_rate = len([r for r in subset if r['sys'] >= 130 or r['dia'] >= 85]) / len(subset) * 100
    print(f"  {desc}: SBP={sys_avg:.1f}, DBP={dia_avg:.1f}, "
          f"T_max={t_max_avg:.1f}℃, T_min={t_min_avg:.1f}℃, "
          f"高血压比例={hyper_rate:.1f}%, n={len(subset)}")

# Various conditions
describe_condition("最低温<-5℃的极寒天",
    [r for r in measured if r['t_min'] < -5])
describe_condition("最高温<5℃的寒冬日",
    [r for r in measured if r['t_max'] < 5])
describe_condition("温差>15℃的大温差日",
    [r for r in measured if r['t_max'] - r['t_min'] > 15])
describe_condition("最低温>25℃的酷暑夜",
    [r for r in measured if r['t_min'] > 25])
describe_condition("10≤T_max≤20 舒适日",
    [r for r in measured if 10 <= r['t_max'] <= 20])

# ---- 10. Low temp + large temp swing combination ----
print(f"\n=== 复合条件: 低温+大温差 vs 单纯低温 ===")
cold_big_swing = [r for r in measured if r['t_min'] < 0 and (r['t_max'] - r['t_min']) > 15]
cold_small_swing = [r for r in measured if r['t_min'] < 0 and (r['t_max'] - r['t_min']) <= 10]
if cold_big_swing:
    describe_condition("低温+大温差(>15℃)", cold_big_swing)
if cold_small_swing:
    describe_condition("低温+小温差(≤10℃)", cold_small_swing)

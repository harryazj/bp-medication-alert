#!/usr/bin/env python3
"""Merge blood pressure and temperature data into a single daily table."""

import csv
from collections import defaultdict
from datetime import date, timedelta

# ---- Step 1: Read BP data ----
bp_by_date = defaultdict(list)  # date -> [(systolic, diastolic), ...]

with open('/Users/lichangda/Downloads/血压记录.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        d = row['日期'].strip()
        s = int(row['高压(收缩压)'])
        dia = int(row['低压(舒张压)'])
        bp_by_date[d].append((s, dia))

# ---- Step 2: Read temperature data ----
temp_by_date = {}  # date -> (max_temp, min_temp)

with open('/Users/lichangda/Downloads/西安气温数据.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        d = row['日期'].strip()
        max_t = int(row['最高温度(℃)'])
        min_t = int(row['最低温度(℃)'])
        temp_by_date[d] = (max_t, min_t)

# ---- Step 3: Merge ----
start_date = date(2024, 2, 15)
end_date = date(2026, 5, 22)

records = []
current = start_date

while current <= end_date:
    date_str = current.isoformat()

    # Temperature (always available in the range)
    max_t, min_t = temp_by_date.get(date_str, (None, None))

    bp_list = bp_by_date.get(date_str, [])

    if bp_list:
        # Day with BP records: average all readings
        avg_sys = round(sum(s for s, _ in bp_list) / len(bp_list))
        avg_dia = round(sum(d for _, d in bp_list) / len(bp_list))
        count = len(bp_list)
    else:
        # No BP: look back for "normal" records (sys < 130 AND dia < 85)
        normal_readings = []
        lookback = current - timedelta(days=1)
        while not normal_readings and lookback >= start_date:
            lookback_str = lookback.isoformat()
            if lookback_str in bp_by_date:
                normal_readings = [(s, d) for s, d in bp_by_date[lookback_str]
                                   if s < 130 and d < 85]
            lookback -= timedelta(days=1)

        if normal_readings:
            avg_sys = round(sum(s for s, _ in normal_readings) / len(normal_readings))
            avg_dia = round(sum(d for _, d in normal_readings) / len(normal_readings))
        else:
            # No normal readings found at all (edge case)
            avg_sys = None
            avg_dia = None
        count = 0  # filled value, not measured

    records.append({
        'date': date_str,
        'max_temp': max_t,
        'min_temp': min_t,
        'systolic': avg_sys,
        'diastolic': avg_dia,
        'count': count,
    })

    current += timedelta(days=1)

# ---- Step 4: Write CSV ----
output_path = '/Users/lichangda/Downloads/血压气温合并.csv'
with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['日期', '血压高压(收缩压)', '血压低压(舒张压)',
                     '气温高温(℃)', '气温低温(℃)', '当天血压记录数'])
    for r in records:
        writer.writerow([
            r['date'],
            r['systolic'] if r['systolic'] is not None else '',
            r['diastolic'] if r['diastolic'] is not None else '',
            r['max_temp'],
            r['min_temp'],
            r['count'],
        ])

# ---- Stats ----
total = len(records)
measured = sum(1 for r in records if r['count'] > 0)
filled = sum(1 for r in records if r['count'] == 0 and r['systolic'] is not None)
unfilled = sum(1 for r in records if r['systolic'] is None)

print(f"日期范围: {start_date} ~ {end_date}")
print(f"总天数: {total}")
print(f"有血压实测: {measured}")
print(f"无血压但填充了(BP正常): {filled}")
print(f"无法填充(BP空): {unfilled}")
print(f"输出文件: {output_path}")

# Show some sample rows
print("\n前10行:")
for r in records[:10]:
    print(f"  {r['date']} | sys={r['systolic']} dia={r['diastolic']} | "
          f"temp={r['max_temp']}/{r['min_temp']} | count={r['count']}")

print("\n后5行:")
for r in records[-5:]:
    print(f"  {r['date']} | sys={r['systolic']} dia={r['diastolic']} | "
          f"temp={r['max_temp']}/{r['min_temp']} | count={r['count']}")

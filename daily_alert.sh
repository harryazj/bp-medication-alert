#!/bin/bash
# 血压用药每日PK预警任务 (通过Claude CLI非交互模式)
# 日志: ~/bp-alert-daily.log

export https_proxy=http://127.0.0.1:6789
export http_proxy=http://127.0.0.1:6789
LOG="$HOME/bp-alert-daily.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"

/opt/homebrew/bin/claude -p --brief "血压用药每日PK预警：

1. WebSearch搜索'西安未央天气预报7天'，获取最新7天天气预报（最高温、最低温、天气）

2. 读取 /Users/lichangda/Downloads/血压气温合并.csv 获取最近3天气温和血压

3. 读取 /tmp/pk_alert_engine.py 中的PK引擎代码，用最新预报数据更新 forecast_raw 参数

4. 执行PK分析，输出未来7天逐日推荐药量

5. 如有预警（降温≥5℃黄色、Tmax<10℃橙色、Tmax<5℃红色），输出【预警】标记

6. 无预警则输出'未来一周无预警，维持当前剂量'

完成后只输出'OK'结束。" >> "$LOG" 2>&1

echo "---" >> "$LOG"
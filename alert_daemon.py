#!/usr/bin/env python3
"""
BP Alert Scheduler Daemon
Background process that runs daily_pk_alert.py at 20:33 each day.
Overcomes macOS passwd/cron/launchd limitations.
"""
import subprocess
import time
import os
import sys
from datetime import datetime

ALERT_SCRIPT = "/Users/lichangda/bp-medication-alert/daily_pk_alert.py"
LOG_FILE = os.path.expanduser("~/bp-daemon.log")


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")


def run_alert():
    log("Running daily alert...")
    try:
        result = subprocess.run(
            ["/usr/bin/python3", ALERT_SCRIPT],
            capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            log(f"OK\n{result.stdout}")
        else:
            log(f"ERROR (exit={result.returncode})\n{result.stderr}")
    except Exception as e:
        log(f"EXCEPTION: {e}")


def main():
    log("BP Alert Daemon started")
    log(f"PID: {os.getpid()}")
    log(f"Target time: 20:33 daily")

    while True:
        now = datetime.now()
        # Calculate seconds until next 20:33
        target = now.replace(hour=20, minute=33, second=0, microsecond=0)
        if now >= target:
            # Already past today's 20:33, schedule for tomorrow
            from datetime import timedelta
            target = target + timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        log(f"Next run at {target}, waiting {wait_seconds/3600:.1f}h")

        # Sleep until 30 seconds before target (then fine-sleep)
        if wait_seconds > 60:
            time.sleep(wait_seconds - 30)
            # Fine-grained wait
            while datetime.now() < target.replace(second=0):
                time.sleep(1)

        run_alert()
        # Prevent re-trigger within same minute
        time.sleep(60)


if __name__ == "__main__":
    main()

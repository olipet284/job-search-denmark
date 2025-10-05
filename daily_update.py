#!/usr/bin/env python3
"""Run update.py at most once per calendar day.

Stores last successful scrape date in .last_scrape.json (UTC date).
Prints a message to stdout indicating whether a scrape was performed or skipped.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import sys

STATE_FILE = Path(__file__).parent / '.last_scrape.json'
UPDATE_SCRIPT = Path(__file__).parent / 'update.py'

def read_last_date():
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return data.get('last_date')
    except Exception:
        return None

def write_last_date(date_str: str):
    try:
        STATE_FILE.write_text(json.dumps({'last_date': date_str, 'timestamp': datetime.now(timezone.utc).isoformat()}))
    except Exception as e:
        print(f"Warning: could not write state file: {e}", file=sys.stderr)

def main():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    last = read_last_date()
    if last == today:
        print(f"[daily_update] Already scraped today ({today}); skipping.")
        return 0
    print(f"[daily_update] Last scrape: {last or 'never'} -> running update.py now (date {today})...")
    # Run the update script in a subprocess so its stdout is streamed
    try:
        proc = subprocess.run([sys.executable, str(UPDATE_SCRIPT)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[daily_update] update.py failed with return code {e.returncode}", file=sys.stderr)
        return e.returncode
    write_last_date(today)
    print(f"[daily_update] Completed scrape and recorded date {today}.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

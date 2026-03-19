"""debug_ts_fix.py – Verify conversation-history ISO timestamps are applied per item."""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

import chatgpt_extractor
from datetime import datetime, timezone

paths = chatgpt_extractor.discover_paths()
ls_dir = paths.get('ls', '')
print(f'LS dir: {ls_dir}')

results = chatgpt_extractor._scan_ls_conversation_history(ls_dir)
print(f'\nconversation-history entries: {len(results)}\n')

for r in sorted(results, key=lambda x: x['update_time'], reverse=True)[:15]:
    ts = r['update_time']
    if ts > 0:
        dt = datetime.fromtimestamp(ts + 5.5*3600, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S IST')
    else:
        dt = 'N/A'
    print(f"  {dt} | {r.get('title','')}")

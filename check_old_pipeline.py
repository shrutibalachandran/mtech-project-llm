"""check_old_pipeline.py – Analyze old RECOVERED_CHATGPT_GROUPED.json for unique data."""
import json, sys, io, re
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('reports/RECOVERED_CHATGPT_GROUPED.json', encoding='utf-8') as f:
    data = json.load(f)

items = data if isinstance(data, list) else data.get('items', [])
print(f'Total items: {len(items)}')

# Count unique conversation IDs
cids = set()
no_cid = 0
titles = set()
has_messages = 0
has_real_msgs = 0

for item in items:
    cid = item.get('conversation_id', '')
    title = item.get('title', '')
    if cid:
        cids.add(cid)
    else:
        no_cid += 1
    if title:
        titles.add(title)
    
    msgs = item.get('messages', [])
    if msgs:
        has_messages += 1
        # Check for real content (not JSON noise)
        real = [m for m in msgs if m.get('snippet') and 
                '{"conversation_id"' not in m.get('snippet','') and
                len(m.get('snippet','')) > 30]
        if real:
            has_real_msgs += 1

print(f'Unique CIDs: {len(cids)}')
print(f'No CID entries: {no_cid}')
print(f'Unique titles: {len(titles)}')
print(f'With messages: {has_messages}')
print(f'With REAL message content: {has_real_msgs}')
print()

# Show timestamp range
times = []
for item in items:
    ut = item.get('latest_update') or item.get('update_time') or 0
    if isinstance(ut, (int, float)) and ut > 1e9:
        times.append(ut)

if times:
    oldest = min(times)
    newest = max(times)
    print(f'Time range:')
    print(f'  Oldest: {datetime.fromtimestamp(oldest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M IST")}')
    print(f'  Newest: {datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%d %H:%M IST")}')

# Show unique titles
print(f'\nAll unique titles ({len(titles)}):')
for t in sorted(titles):
    print(f'  {t}')

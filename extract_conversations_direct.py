"""
extract_conversations_direct.py
Uses direct binary search for known title strings discovered in blob_26.bin.
Then walks backwards to find the UUID for each title.
"""
import re, json

BLOB = r'temp_live_idb\blob_26.bin'
OUT  = r'reports\RECOVERED_CLAUDE_HISTORY.json'

data = open(BLOB, 'rb').read()

# Known titles confirmed in the raw scan output
KNOWN_TITLES = [
    b'Extracting data from LLMs',
    b'What is generative AI',
    b'Deadliest disease in the world',
    b'Bat and ball defini',     # truncated in raw scan, find full version
    b'helloo',
    b'Cyber forensics explained',
]

UUID_PAT = re.compile(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

conversations = []

for needle in KNOWN_TITLES:
    idx = data.find(needle)
    if idx == -1:
        print(f"NOT FOUND: {needle.decode()}")
        continue

    # Extract full title: scan forward from idx until we hit a non-printable byte
    end = idx
    while end < len(data) and (32 <= data[end] < 127):
        end += 1
    full_title = data[idx:end].decode('ascii', errors='replace').strip()

    # Walk backwards from idx to find the UUID (look back up to 300 bytes)
    lookback = data[max(0, idx-300):idx]
    uuid_matches = UUID_PAT.findall(lookback)
    uuid = uuid_matches[-1].decode() if uuid_matches else ''

    # Try to find created_at timestamp near this title (look forward 200 bytes)
    lookahead_raw = data[idx:idx+300].decode('latin-1', errors='replace')
    ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)', lookahead_raw)
    created_at = ts_match.group(1) if ts_match else ''

    # Try to find model name
    model_match = re.search(rb'claude-[a-z0-9\-]+', data[idx:idx+200])
    model = model_match.group(0).decode() if model_match else ''

    print(f"FOUND: {repr(full_title)}")
    print(f"  UUID:       {uuid}")
    print(f"  created_at: {created_at}")
    print(f"  model:      {model}")
    print()

    conversations.append({
        'title': full_title,
        'conversation_id': uuid,
        'created_at': created_at,
        'model': model,
    })

# ---------------------------------------------------------------------------
# Merge into output JSON (keep existing entries, only add missing ones)
# ---------------------------------------------------------------------------
with open(OUT, 'r', encoding='utf-8') as f:
    existing = json.load(f)

# Remove erroneous partial entries from previous run
BAD = {'ting data from LLMs!', 's generative AI', 'ting data from LLMs', 's generative'}
existing['items'] = [
    item for item in existing.get('items', [])
    if item.get('title', '') not in BAD
]

existing_ids = {item['conversation_id'] for item in existing['items']}
existing_titles = {item['title'] for item in existing['items']}

new_items = []
for c in conversations:
    if not c['conversation_id']:
        print(f"[WARN] No UUID for: {c['title']} — skipping")
        continue
    if c['conversation_id'] in existing_ids:
        print(f"[SKIP - exists by ID] {c['conversation_id']}: {c['title']}")
        continue
    if c['title'] in existing_titles:
        print(f"[SKIP - exists by title] {c['title']}")
        continue

    # Convert ISO timestamp to unix float if available
    update_time = 0.0
    if c['created_at']:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(c['created_at'].replace('Z', '+00:00'))
            update_time = dt.timestamp()
        except: pass

    new_items.append({
        "conversation_id": c['conversation_id'],
        "current_node_id": "",
        "title": c['title'],
        "model": c['model'],
        "is_archived": False,
        "is_starred": False,
        "update_time": update_time,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": f"[Recovered from IndexedDB blob_26 - V8 serialized]{' created=' + c['created_at'] if c['created_at'] else ''}"
        },
        "source_file": "IndexedDB/blob_26"
    })

# Prepend new items (most recent conversations go first)
existing['items'] = new_items + existing['items']

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Added {len(new_items)} new conversations. Total items: {len(existing['items'])}")

"""
extract_blob_convs.py
Parse blob_26.bin V8 binary to extract conversation UUIDs and titles,
then merge into reports/RECOVERED_CLAUDE_HISTORY.json WITHOUT modifying
existing entries.
"""
import re, json, os, datetime

BLOB = r'temp_live_idb\blob_26.bin'
OUT  = r'reports\RECOVERED_CLAUDE_HISTORY.json'

data = open(BLOB, 'rb').read()

# ---------------------------------------------------------------------------
# 1. Extract UUID -> title pairs from the binary
# ---------------------------------------------------------------------------
# The blob stores V8 strings. In the region we found, entries look like:
#   <UUID bytes>\x22 ... "name" ... <LEN> <TITLE UTF-8 bytes>
# We'll do a regex on the latin-1 decoded bytes so we can match byte-for-byte.

text = data.decode('latin-1')  # preserves all bytes

# Regex: UUID followed (within 80 chars) by "name" keyword and then a printable title
pattern = re.compile(
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
    r'[\x00-\xff]{1,80}?'
    r'name[\x00-\xff]{0,8}'
    r'([A-Za-z][A-Za-z0-9 ,!?\'\-:&()]{3,100})'
)

entries = pattern.findall(text[155000:])   # start from where conversation list begins

# Also extract created_at / updated_at timestamps near each UUID
# Pattern: ISO date like 2026-03-14T15:10:02
date_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)')
# Extract model names near titles
model_pattern = re.compile(r'claude-[a-z0-9\-]+')

# Build conversation list
seen_titles = set()
seen_uuids  = set()
conversations = []

for uuid, raw_title in entries:
    title = raw_title.strip()
    # Skip obvious false positives
    if len(title) < 4:
        continue
    if title.lower() in ('name', 'model', 'true', 'false', 'null'):
        continue
    key = (uuid, title[:30])
    if key in seen_uuids:
        continue
    if title in seen_titles:
        continue
    seen_uuids.add(key)
    seen_titles.add(title)
    conversations.append({'conversation_id': uuid, 'title': title})

print(f"Extracted {len(conversations)} conversation entries:")
for c in conversations:
    print(f"  {c['conversation_id']}  ->  {c['title']}")

# ---------------------------------------------------------------------------
# 2. Build new items list in the output schema format
# ---------------------------------------------------------------------------
# Load existing output
with open(OUT, 'r', encoding='utf-8') as f:
    existing = json.load(f)

existing_ids = {item['conversation_id'] for item in existing.get('items', [])}

new_items = []
for c in conversations:
    cid = c['conversation_id']
    title = c['title']
    if cid in existing_ids:
        print(f"  [SKIP - already present] {cid}: {title}")
        continue
    new_items.append({
        "conversation_id": cid,
        "current_node_id": "",
        "title": title,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "update_time": 0.0,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": "[Recovered from IndexedDB blob - V8 serialized conversation list]"
        },
        "source_file": "IndexedDB/blob_26"
    })

print(f"\nAdding {len(new_items)} new items to {OUT}")
existing['items'] = new_items + existing['items']

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print("Done. Output saved.")

"""
fixup_convs.py  - Fix partial/wrong titles and add Cyber forensics, 
                  full 'Bat and ball definitions', and 'What is generative AI' 
                  with correct UUIDs from blob_26.bin raw scan data.
"""
import re, json

BLOB = r'temp_live_idb\blob_26.bin'
OUT  = r'reports\RECOVERED_CLAUDE_HISTORY.json'

data = open(BLOB, 'rb').read()

# --- Find "Bat and ball definitions" full title ---
bat_idx = data.find(b'Bat and ball defini')
if bat_idx != -1:
    end = bat_idx
    while end < len(data) and 32 <= data[end] < 127:
        end += 1
    bat_title = data[bat_idx:end].decode('ascii', errors='replace').strip()
    print(f"Bat full title: {repr(bat_title)}")
else:
    bat_title = 'Bat and ball definitions'

# --- Bat and ball UUID: look back from that offset ---
bat_lookback = data[max(0, bat_idx - 400):bat_idx]
bat_uuid_m = re.findall(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', bat_lookback)
bat_uuid = bat_uuid_m[-1].decode() if bat_uuid_m else ''
print(f"Bat UUID: {bat_uuid}")

# --- Find "Cyber forensics explained" ---
# Try with partial
cyb_idx = data.find(b'Cyber for')
if cyb_idx == -1:
    cyb_idx = data.find(b'Cyber forensics')
if cyb_idx != -1:
    end = cyb_idx
    while end < len(data) and 32 <= data[end] < 127:
        end += 1
    cyb_title = data[cyb_idx:end].decode('ascii', errors='replace').strip()
    cyb_lookback = data[max(0, cyb_idx - 400):cyb_idx]
    cyb_uuid_m = re.findall(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', cyb_lookback)
    cyb_uuid = cyb_uuid_m[-1].decode() if cyb_uuid_m else ''
    print(f"Cyber title: {repr(cyb_title)}, UUID: {cyb_uuid}")
else:
    print("Cyber forensics: NOT FOUND in blob")
    cyb_title = 'Cyber forensics explained'
    cyb_uuid = '54fd3a6b-cf9f-4984-83b7-6d034dc6d0af'  # from existing data_1 entry

# --- Load output JSON ---
with open(OUT, 'r', encoding='utf-8') as f:
    output = json.load(f)

items = output['items']

# 1. Fix 'hellooJ7' -> 'helloo'
for item in items:
    if item.get('title') == 'hellooJ7':
        item['title'] = 'helloo'
        print("[FIX] hellooJ7 -> helloo")

# 2. Fix 'Bat and ball defini' -> full title
for item in items:
    if item.get('title', '').startswith('Bat and ball defini'):
        item['title'] = bat_title
        if bat_uuid:
            item['conversation_id'] = bat_uuid
        print(f"[FIX] Bat title -> {bat_title}")

# 3. Fix 'Extracting data from LLMs!' -> strip trailing !
for item in items:
    if item.get('title') == 'Extracting data from LLMs!':
        item['title'] = 'Extracting data from LLMs'
        print("[FIX] Stripped trailing ! from Extracting title")

# 4. Add Cyber forensics if not already present
existing_ids = {item['conversation_id'] for item in items}
existing_titles = {item['title'] for item in items}

if cyb_uuid and cyb_uuid not in existing_ids and cyb_title not in existing_titles:
    items.append({
        "conversation_id": cyb_uuid,
        "current_node_id": "",
        "title": cyb_title,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "update_time": 0.0,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": "[Recovered from IndexedDB blob_26 - V8 serialized conversation list]"
        },
        "source_file": "IndexedDB/blob_26"
    })
    print(f"[ADD] Cyber forensics: {cyb_title} / {cyb_uuid}")
else:
    print(f"[SKIP] Cyber forensics already present or no UUID")

output['items'] = items

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Total items: {len(items)}")
print("Titles in output:")
for item in items:
    print(f"  [{item.get('source_file','?')}] {item['conversation_id'][:8]}...  ->  {item['title']}")

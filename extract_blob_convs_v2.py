"""
extract_blob_convs_v2.py
Parse blob_26.bin with tighter windowed search around known byte offsets
to extract full conversation titles. Also undo the bad partial entries 
written by v1 and rewrite the full correct list.
"""
import re, json, os

BLOB = r'temp_live_idb\blob_26.bin'
OUT  = r'reports\RECOVERED_CLAUDE_HISTORY.json'

data = open(BLOB, 'rb').read()

# We know from the raw scan the conversations are in the region 160000-162000
# Extract that window decoded as latin-1 (byte-preserving)
window = data[158000:164000].decode('latin-1', errors='replace')

# The raw scan output showed this kind of pattern:
#   UUID" .name". TITLE .  ...  created_at". ISO_DATE
# Use a simpler regex: find UUIDs and grab the printable text that follows

# Manually-verified direct extraction based on raw byte output we captured:
# Pattern: after UUID comes \x22 (") and within ~100 bytes comes the title ended by \x21 or similar
uuid_title_pattern = re.compile(
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'  # UUID
    r'[^\n]{1,200}?'            # skip garbage bytes  
    r'\.([A-Z][A-Za-z0-9 ,!?\'\-:&()/]{3,120})'  # title starts with capital letter
)

matches = uuid_title_pattern.findall(window)

# Deduplicate cleanly
seen = set()
conversations = []
for uuid, raw_title in matches:
    title = raw_title.rstrip('!').strip()
    if title in seen or len(title) < 4:
        continue
    # Filter out false positives (known non-conversation strings)
    if any(x in title for x in ['Anthropic', 'Claude', 'CRITICAL', 'DEFAULT', 'BEHAVIOR', 
                                  'REQUESTED', 'SUCCESS', 'NEDM', 'Turn', 'Context Window',
                                  'Thin', 'Try', 'Create apps', 'API', 'SKILL']):
        continue
    seen.add(title)
    conversations.append({'conversation_id': uuid, 'title': title})

print("=== Extracted conversations ===")
for c in conversations:
    print(f"  {c['conversation_id']}  ->  {repr(c['title'])}")

# ---------------------------------------------------------------------------
# Load existing output and rebuild cleanly
# ---------------------------------------------------------------------------
with open(OUT, 'r', encoding='utf-8') as f:
    existing = json.load(f)

# Remove the bad partial entries written by v1 (titles starting mid-word)
BAD_PARTIAL_TITLES = {'ting data from LLMs!', 's generative AI'}
clean_items = [item for item in existing.get('items', [])
               if item.get('title', '') not in BAD_PARTIAL_TITLES]

# Build new items for conversations not already in the clean list
existing_ids = {item['conversation_id'] for item in clean_items}
new_items = []
for c in conversations:
    cid = c['conversation_id']
    title = c['title']
    if cid in existing_ids:
        print(f"[SKIP - exists] {cid}: {title}")
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

print(f"\nAdding {len(new_items)} new items.")

existing['items'] = new_items + clean_items

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(existing, f, indent=2, ensure_ascii=False)

print("Done.")

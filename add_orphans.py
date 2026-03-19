"""
add_orphans.py - Add the 234 orphaned entries (including deleted chats) to the recovered output.

ORPHANED_CID_DETAILS.json has entries like:
  { "cid": "...", "titles": [...], "sources": [...], "snippets": [...] }

These are conversation IDs found in LDB/cache but whose content couldn't be fully 
reconstructed. The CID and best-available title are enough for forensic identification.
Entries that appear only in ORPHANED (not in restored cache) are likely DELETED conversations.
"""
import json
from datetime import datetime, timezone

BASE = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
OUT  = BASE + r"\reports\RECOVERED_CHATGPT_HISTORY.json"

def ts_to_iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00","Z")
    except Exception:
        return "1970-01-01T00:00:00Z"

# Load current output
with open(OUT, encoding='utf-8') as f:
    rec = json.load(f)
items = rec.get('items', [])
existing_cids = {i['conversation_id'] for i in items if i.get('conversation_id')}
print(f"Starting with {len(items)} items, {len(existing_cids)} unique CIDs")

# Load ORPHANED_CID_DETAILS
with open(BASE + r'\ORPHANED_CID_DETAILS.json', encoding='utf-8') as f:
    orphaned = json.load(f)

# Load HARVESTED_CIDS (just UUID strings)
with open(BASE + r'\HARVESTED_CIDS.json', encoding='utf-8') as f:
    harvested = json.load(f)
harvested_set = set(s.strip().lower() for s in harvested if isinstance(s, str))

added = 0
for e in orphaned:
    cid = e.get('cid', '').strip().lower()
    if not cid or cid in existing_cids:
        continue
    
    titles   = e.get('titles', [])
    snippets = e.get('snippets', [])
    sources  = e.get('sources', [])
    
    # Pick best title
    good_titles = [t for t in titles if t and t.strip() and t.strip() not in ('New chat','')]
    title = good_titles[0] if good_titles else 'New chat'
    
    # Pick snippet - prefer one that doesn't look like raw JSON metadata
    best_snip = ''
    for s in snippets:
        if s and not s.startswith('{"') and not s.startswith('": null'):
            best_snip = s[:300]
            break
    
    # Determine if this is a deleted conversation:
    # It's in ORPHANED but not in existing cache recovery = likely deleted
    is_deleted = cid not in {i['conversation_id'] for i in items}
    
    src = sources[0] if sources else 'ORPHANED_CID_DETAILS.json'
    
    if is_deleted and not best_snip:
        snip_text = f"[Deleted conversation] title={repr(title)} – recovered from LevelDB orphan index"
    elif best_snip:
        snip_text = best_snip
    else:
        snip_text = f"[No cached content] – conversation_id recovered from LevelDB index"
    
    item = {
        "conversation_id":  cid,
        "current_node_id":  "",
        "title":            title,
        "model":            "",
        "is_archived":      False,
        "is_starred":       False,
        "is_deleted":       is_deleted,
        "update_time":      0.0,
        "payload": {
            "kind":       "message",
            "message_id": "",
            "snippet":    snip_text,
        },
        "source_file": src,
        "recovery_note": (
            "Recovered from LevelDB orphan index – possible deleted conversation"
            if is_deleted else
            "Recovered from LevelDB orphan index"
        ),
    }
    items.append(item)
    existing_cids.add(cid)
    added += 1

print(f"Added {added} orphaned entries")

# Also add harvested CIDs that are still missing (no title available)
missing_cids_no_title = harvested_set - existing_cids
print(f"Harvested CIDs with no title/entry at all: {len(missing_cids_no_title)}")
# These are UUID-only – add as minimal placeholders only if there are <= 50
if len(missing_cids_no_title) <= 50:
    for cid in sorted(missing_cids_no_title):
        item = {
            "conversation_id":  cid,
            "current_node_id":  "",
            "title":            "Unknown (deleted/orphaned conversation)",
            "model":            "",
            "is_archived":      False,
            "is_starred":       False,
            "is_deleted":       True,
            "update_time":      0.0,
            "payload": {
                "kind":       "message",
                "message_id": "",
                "snippet":    "[Deleted conversation] – only conversation_id recovered from LevelDB",
            },
            "source_file": "HARVESTED_CIDS.json",
            "recovery_note": "UUID-only recovery – title and content not recoverable",
        }
        items.append(item)
        added += 1
    print(f"Added {len(missing_cids_no_title)} UUID-only entries")
else:
    print(f"Skipping {len(missing_cids_no_title)} UUID-only entries (too many – likely noise/fragments)")

# Sort: real timestamps first, then no-timestamp entries by title
items.sort(key=lambda x: (float(x.get('update_time') or 0), x.get('title','')), reverse=True)

print(f"\nFinal total: {len(items)} conversations")

deleted_count = sum(1 for i in items if i.get('is_deleted'))
with_content  = sum(1 for i in items if not (
    i.get('payload',{}).get('snippet','').startswith('[No cached') or
    i.get('payload',{}).get('snippet','').startswith('[Deleted')
))
print(f"  With real content:     {with_content}")
print(f"  Flagged as deleted:    {deleted_count}")
print(f"  Placeholder/no-cache:  {len(items)-with_content}")

# Write
output = {
    "_forensic_notes": rec.get("_forensic_notes",""),
    "_recovery_additions": (
        f"Final merge: {len(items)} unique conversations from 7 sources "
        f"including {deleted_count} deleted/orphaned conversations recovered from LevelDB."
    ),
    "items": items,
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\n[DONE] Written to: {OUT}")

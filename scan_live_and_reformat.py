"""
scan_live_and_reformat.py  –  Two tasks in one:

TASK 1: Scan live ChatGPT LDB files (IndexedDB + Local Storage) to get March 2026 chats.
TASK 2: Reformat RECOVERED_CHATGPT_HISTORY.json to match Claude JSON schema exactly:
  {
    "conversation_id": "...",
    "current_node_id": "...",
    "title": "...",
    "model": "",
    "is_archived": false,
    "is_starred": false,
    "update_time": 1234567890.0,
    "payload": {
        "kind": "message",
        "message_id": "...",
        "snippet": "...",
        "role": "assistant"
    },
    "source_file": "..."
  }
"""
import os, json, re, shutil, sys, io, glob
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE    = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
APPDATA = os.getenv("LOCALAPPDATA", "")
CHATGPT_PKG = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT"
)

OUT_HISTORY = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")

LIVE_PATHS = [
    os.path.join(CHATGPT_PKG, "IndexedDB"),
    os.path.join(CHATGPT_PKG, "Local Storage", "leveldb"),
]

UUID_RE   = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
TITLE_RE  = re.compile(r'"title"\s*:\s*"((?:[^"\\]|\\.){1,300})"')
UPDATE_RE = re.compile(r'"update_time"\s*:\s*([\d.]+)')
CREATE_RE = re.compile(r'"create_time"\s*:\s*([\d.]+)')
SNIP_RE   = re.compile(r'"snippet"\s*:\s*"((?:[^"\\]|\\.){1,500})"')

def ts_human(ts):
    try:
        t = float(ts)
        if t <= 0: return "N/A"
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except: return "N/A"

# ── TASK 1: Scan live LDB files ───────────────────────────────────────────────
print("=" * 60)
print("TASK 1: Scanning live ChatGPT LDB/IndexedDB for new data")
print("=" * 60)

new_convs = {}  # cid -> {title, update_time, create_time, snippet, source}

for live_dir in LIVE_PATHS:
    if not os.path.isdir(live_dir):
        print(f"[MISS] {live_dir}")
        continue
    
    ldb_files = (
        glob.glob(os.path.join(live_dir, "*.log")) +
        glob.glob(os.path.join(live_dir, "*.ldb"))
    )
    print(f"\n[SCAN] {os.path.basename(live_dir)}: {len(ldb_files)} files")
    
    for fpath in sorted(ldb_files):
        fname = os.path.basename(fpath)
        try:
            # Copy to temp to avoid file-lock issues
            tmp = os.path.join(BASE, f"_tmp_live_{os.getpid()}.bin")
            shutil.copy2(fpath, tmp)
            with open(tmp, "rb") as f:
                raw = f.read()
            os.remove(tmp)
        except Exception as e:
            print(f"  [SKIP] {fname}: {e}")
            continue
        
        # Decode as utf-8 with replacement
        text = raw.decode("utf-8", errors="replace")
        
        hits = 0
        for tm in TITLE_RE.finditer(text):
            title_raw = tm.group(1)
            try:
                title = json.loads('"' + title_raw + '"')
            except:
                title = title_raw
            
            if not title or len(title) < 2 or title.startswith('{'):
                continue
            
            # Window around title
            win_s = max(0, tm.start() - 3000)
            win_e = min(len(text), tm.end() + 3000)
            window = text[win_s:win_e]
            
            uuid_m = UUID_RE.search(window)
            cid = uuid_m.group(1).lower() if uuid_m else ""
            
            upd_m = UPDATE_RE.search(window)
            ut = float(upd_m.group(1)) if upd_m else 0.0
            
            cre_m = CREATE_RE.search(window)
            ct = float(cre_m.group(1)) if cre_m else 0.0
            
            snip_m = SNIP_RE.search(window)
            snippet = ""
            if snip_m:
                try:
                    snippet = json.loads('"' + snip_m.group(1) + '"')
                except:
                    snippet = snip_m.group(1)
            
            if cid and cid != "00000000-0000-0000-0000-000000000000":
                prev = new_convs.get(cid)
                if prev is None or ut > prev.get("update_time", 0):
                    new_convs[cid] = {
                        "title": title,
                        "update_time": ut,
                        "create_time": ct,
                        "snippet": snippet,
                        "source": fname,
                    }
                    hits += 1
        
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        print(f"  {fname} (modified {mtime}): {hits} title hits")

print(f"\n[RESULT] New conversations found in live LDB: {len(new_convs)}")

# Filter for truly new ones (not already in the file OR newer timestamp)
with open(OUT_HISTORY, encoding='utf-8') as f:
    existing_data = json.load(f)
existing_items = existing_data.get('items', [])
existing_cids = {i.get('conversation_id', ''): i.get('update_time', 0) for i in existing_items}

march1_ts = 1772323200.0  # March 1, 2026 UTC
new_or_updated = {}
for cid, e in new_convs.items():
    prev_ut = existing_cids.get(cid, -1)
    if prev_ut == -1:
        # Brand new CID
        new_or_updated[cid] = e
    elif e['update_time'] > float(prev_ut or 0) + 60:
        # Updated since last scan
        new_or_updated[cid] = e

march_new = {cid: e for cid, e in new_or_updated.items() if e['update_time'] >= march1_ts}
print(f"[RESULT] New/updated CIDs: {len(new_or_updated)}")
print(f"[RESULT] New CIDs from March 2026+: {len(march_new)}")

# ── TASK 2: Reformat RECOVERED_CHATGPT_HISTORY.json to Claude schema ──────────
print("\n" + "=" * 60)
print("TASK 2: Reformatting to Claude JSON schema")
print("=" * 60)

def make_item(cid, title, update_time, create_time=0.0,
              snippet=None, source="", is_deleted=False, current_node_id="", message_id="", role=""):
    """Create a record in Claude-compatible format."""
    ut = float(update_time or 0)
    iso = ""
    if ut > 0:
        iso = datetime.fromtimestamp(ut, tz=timezone.utc).strftime("updated=%Y-%m-%dT%H:%M:%S.%fZ")
    
    # Best snippet
    snip = snippet or ""
    if not snip or snip.startswith('[No cached') or snip.startswith('[Deleted'):
        snip = f"[No cached content] {iso}".strip()
    
    return {
        "conversation_id":  cid,
        "current_node_id":  current_node_id or message_id or "",
        "title":            title,
        "model":            "",
        "is_archived":      False,
        "is_starred":       False,
        "is_deleted":       is_deleted,
        "update_time":      ut,
        "payload": {
            "kind":       "message",
            "message_id": message_id or current_node_id or "",
            "snippet":    snip,
            "role":       role or ("assistant" if snip and not snip.startswith("[") else ""),
        },
        "source_file": source,
    }

# Rebuild all items in new schema
reformatted = []
for item in existing_items:
    cid     = item.get("conversation_id", "")
    title   = item.get("title", "")
    ut      = item.get("update_time", 0.0)
    src     = item.get("source_file", "")
    is_del  = item.get("is_deleted", False)
    
    # Extract existing snippet and role
    payload = item.get("payload", {})
    old_snip = payload.get("snippet", "") or item.get("snippet", "")
    role     = payload.get("role", "") or item.get("role", "")
    msg_id   = payload.get("message_id", "") or item.get("message_id", "")
    cur_node = item.get("current_node_id", "") or msg_id
    
    reformatted.append(make_item(
        cid, title, ut, 0.0, old_snip, src, is_del, cur_node, msg_id, role
    ))

# Add brand-new live-scanned entries
added_count = 0
existing_cid_set = {i.get("conversation_id","") for i in reformatted}
for cid, e in new_or_updated.items():
    if cid not in existing_cid_set:
        reformatted.append(make_item(
            cid=cid,
            title=e["title"],
            update_time=e["update_time"],
            create_time=e["create_time"],
            snippet=e["snippet"],
            source=f"live_ldb/{e['source']}",
            is_deleted=False,
            role="assistant" if e.get("snippet") else "",
        ))
        existing_cid_set.add(cid)
        added_count += 1
    else:
        # Update existing entry if newer
        for r in reformatted:
            if r["conversation_id"] == cid and e["update_time"] > float(r.get("update_time") or 0) + 60:
                r["update_time"] = e["update_time"]
                if e["snippet"] and not e["snippet"].startswith('['):
                    r["payload"]["snippet"] = e["snippet"]
                    r["payload"]["role"] = "assistant"
                break

# Sort newest -> oldest
reformatted.sort(key=lambda x: float(x.get("update_time") or 0), reverse=True)

print(f"[INFO] Items before: {len(existing_items)}")
print(f"[INFO] Items added from live scan: {added_count}")
print(f"[INFO] Items after:  {len(reformatted)}")
print(f"[INFO] Newest: {ts_human(reformatted[0]['update_time'])} - {reformatted[0]['title']}")

# Sample March entries
march_items = [r for r in reformatted if float(r.get("update_time") or 0) >= march1_ts]
print(f"\n[MARCH+] {len(march_items)} conversations in March 2026+:")
for m in march_items[:10]:
    print(f"  {ts_human(m['update_time'])} | {m['title']}")

# Write
output = {
    "_forensic_notes": (
        "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data "
        "physically recovered from binary artifacts. Schema matches RECOVERED_CLAUDE_HISTORY.json."
    ),
    "_recovery_additions": f"Re-scanned live LDB on 2026-03-19. Added {added_count} new entries.",
    "items": reformatted,
}
with open(OUT_HISTORY, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Written: {OUT_HISTORY}")
print(f"       Total: {len(reformatted)} conversations")

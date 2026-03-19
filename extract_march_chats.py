"""
extract_march_chats.py  –  Extract March 2026 ChatGPT conversations from Local Storage LDB.

Key findings:
  - Timestamps stored as milliseconds (1773xxxxxxxxx), not seconds
  - Titles present as "title":<string> in KB-sized JSON-like blocks
  - CIDs present as 6916xxxx style UUIDs nearby
  - Files: 000821.ldb (Mar 16), 000823.ldb (Mar 17), 000825.log (Mar 19), 000826.ldb (Mar 19)
"""
import os, sys, io, json, re, shutil, glob
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE    = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
APPDATA = os.getenv("LOCALAPPDATA", "")
sys.path.insert(0, BASE)
import forensic_main as fm

LIVE_LS = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "Local Storage", "leveldb"
)
OUT_HISTORY = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")

# ── Regex patterns ────────────────────────────────────────────────────────────
# Millisecond epoch in range Feb 17 2026 – beyond: 1771286400000 to 1780000000000
MS_TS_RE   = re.compile(rb'(177[0-9]{10})')
TITLE_RE   = re.compile(rb'"title"\s*"([^"]{2,300})"')         # Local Storage KV format
TITLE_JSON = re.compile(rb'"title"\s*:\s*"((?:[^"\\]|\\.){2,300})"')  # JSON  
UUID_RE    = re.compile(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
SNIPPET_RE = re.compile(rb'"snippet"\s*:\s*"((?:[^"\\]|\\.){10,500})"')

def decode_b(b):
    try: return json.loads(b'"' + b + b'"')
    except: return b.decode('utf-8', errors='replace')

def ms_to_s(ms_bytes):
    try:
        return float(ms_bytes) / 1000.0
    except: return 0.0

def ts_human(ts):
    try:
        t = float(ts)
        if t <= 0: return "N/A"
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except: return "N/A"

feb17_ms = 1771286400000  # milliseconds

new_convs = {}  # cid -> {title, update_time_s, snippet, source}

files = sorted(glob.glob(os.path.join(LIVE_LS, "*.log"))) + \
        sorted(glob.glob(os.path.join(LIVE_LS, "*.ldb")))

print(f"Scanning {len(files)} files for March 2026 data...\n")

for fpath in files:
    fname = os.path.basename(fpath)
    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
    
    try:
        tmp = fpath + "_tmp_march"
        shutil.copy2(fpath, tmp)
        with open(tmp, "rb") as f:
            raw = f.read()
        os.remove(tmp)
    except Exception as e:
        print(f"  [SKIP] {fname}: {e}")
        continue
    
    buffers = [raw]
    try:
        buffers.extend(fm.try_snappy_decompress(raw))
    except: pass
    
    file_hits = []
    
    for buf in buffers:
        # Method 1: Find ms timestamps first, then look for nearby title+UUID
        for ms_m in MS_TS_RE.finditer(buf):
            ms_val = int(ms_m.group(1))
            if ms_val < feb17_ms:
                continue
            ts_s = ms_val / 1000.0
            
            # Look ±4KB window
            win_s = max(0, ms_m.start() - 4000)
            win_e = min(len(buf), ms_m.end() + 4000)
            win = buf[win_s:win_e]
            
            # Find title
            title = ""
            for pat in [TITLE_RE, TITLE_JSON]:
                tm = pat.search(win)
                if tm:
                    title = decode_b(tm.group(1))
                    break
            
            # Find UUID
            uuid_m = UUID_RE.search(win)
            cid = uuid_m.group(1).decode('ascii').lower() if uuid_m else ""
            
            # Find snippet
            snip_m = SNIPPET_RE.search(win)
            snippet = decode_b(snip_m.group(1)) if snip_m else ""
            
            if title or cid:
                file_hits.append({
                    "cid": cid,
                    "title": title,
                    "update_time": ts_s,
                    "snippet": snippet,
                    "source": fname,
                })
        
        # Method 2: Find titles and search nearby for ms-timestamp
        for pat in [TITLE_RE, TITLE_JSON]:
            for tm in pat.finditer(buf):
                title = decode_b(tm.group(1))
                if not title or len(title) < 2:
                    continue
                win_s = max(0, tm.start() - 4000)
                win_e = min(len(buf), tm.end() + 4000)
                win = buf[win_s:win_e]
                
                # Find nearest ms-timestamp
                best_ts = 0
                for ms_m in MS_TS_RE.finditer(win):
                    ms_val = int(ms_m.group(1))
                    if ms_val >= feb17_ms:
                        best_ts = max(best_ts, ms_val / 1000.0)
                
                uuid_m = UUID_RE.search(win)
                cid = uuid_m.group(1).decode('ascii').lower() if uuid_m else ""
                
                snip_m = SNIPPET_RE.search(win)
                snippet = decode_b(snip_m.group(1)) if snip_m else ""
                
                if best_ts > 0:
                    file_hits.append({
                        "cid": cid,
                        "title": title,
                        "update_time": best_ts,
                        "snippet": snippet,
                        "source": fname,
                    })
    
    print(f"  {fname} ({mtime}): {len(file_hits)} March hits")
    
    # Merge into new_convs dict (keep highest update_time per CID)
    for h in file_hits:
        cid = h["cid"]
        key = cid if cid else h["title"][:40]  # fallback key = title
        
        prev = new_convs.get(key)
        if prev is None or h["update_time"] > prev["update_time"]:
            new_convs[key] = h

print(f"\nTotal unique March+ conversations found: {len(new_convs)}")
print()
for key in sorted(new_convs.keys(), key=lambda k: new_convs[k]['update_time'], reverse=True)[:30]:
    h = new_convs[key]
    print(f"  {ts_human(h['update_time'])} | cid={h['cid'][:20] if h['cid'] else 'N/A'} | title={repr(h['title'][:50])}")

# ── Load existing & merge ─────────────────────────────────────────────────────
with open(OUT_HISTORY, encoding='utf-8') as f:
    existing_data = json.load(f)
existing_items = existing_data.get("items", [])
existing_cids  = {i.get("conversation_id",""): float(i.get("update_time") or 0)
                  for i in existing_items}
existing_titles = {i.get("title","").strip(): i for i in existing_items}

added = 0
updated = 0

def ts_iso(ts):
    try:
        t = float(ts)
        if t <= 0: return ""
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("updated=%Y-%m-%dT%H:%M:%S.%fZ")
    except: return ""

for key, h in new_convs.items():
    cid    = h["cid"]
    title  = h["title"]
    ut     = h["update_time"]
    snip   = h["snippet"]
    src    = f"live_ldb/{h['source']}"
    
    snip_out = snip if snip else f"[No cached content] {ts_iso(ut)}"
    
    new_item = {
        "conversation_id":  cid,
        "current_node_id":  "",
        "title":            title,
        "model":            "",
        "is_archived":      False,
        "is_starred":       False,
        "is_deleted":       False,
        "update_time":      ut,
        "payload": {
            "kind":       "message",
            "message_id": "",
            "snippet":    snip_out,
            "role":       "assistant" if snip else "",
        },
        "source_file": src,
    }
    
    if cid and cid in existing_cids:
        # Update if newer
        if ut > existing_cids[cid] + 60:
            for item in existing_items:
                if item.get("conversation_id") == cid:
                    item["update_time"] = ut
                    if snip and not snip.startswith('['):
                        item["payload"]["snippet"] = snip
                    if title and not item.get("title"):
                        item["title"] = title
                    updated += 1
                    break
    elif title in existing_titles:
        # Same title already exists, update its timestamp if newer  
        item = existing_titles[title]
        if ut > float(item.get("update_time") or 0) + 60:
            item["update_time"] = ut
            if cid and not item.get("conversation_id"):
                item["conversation_id"] = cid
            updated += 1
    else:
        existing_items.append(new_item)
        if cid:
            existing_cids[cid] = ut
        existing_titles[title] = new_item
        added += 1

print(f"\n[MERGE] Added: {added} | Updated: {updated}")

# Sort newest→oldest
existing_items.sort(key=lambda x: float(x.get("update_time") or 0), reverse=True)

print(f"[INFO] Newest: {ts_human(existing_items[0]['update_time'])} - {existing_items[0]['title']}")

output = {
    "_forensic_notes": existing_data.get("_forensic_notes",""),
    "_recovery_additions": f"March 2026 live LDB re-scan: added {added}, updated {updated}.",
    "items": existing_items,
}
with open(OUT_HISTORY, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"[DONE] {OUT_HISTORY}: {len(existing_items)} total conversations")

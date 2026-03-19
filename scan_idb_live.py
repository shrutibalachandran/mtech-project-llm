"""
scan_idb_live.py  –  Use forensic_main.py's existing scanner with Snappy decompression
to properly extract data from the live ChatGPT IndexedDB and Local Storage leveldb,
then merge new March 2026 conversations into RECOVERED_CHATGPT_HISTORY.json.
"""
import os, sys, io, json, re, shutil, glob
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# We need to add the project dir to path to import forensic_main helpers
import importlib.util, types

BASE    = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
APPDATA = os.getenv("LOCALAPPDATA", "")

LIVE_IDB = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "IndexedDB", "https_chatgpt.com_0.indexeddb.leveldb"
)
LIVE_LS = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "Local Storage", "leveldb"
)

OUT_HISTORY = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")

# ── Import Snappy decompress from forensic_main ────────────────────────────────
sys.path.insert(0, BASE)
try:
    import forensic_main as fm
    try_snappy = fm.try_snappy_decompress
    fallback_carve = fm.fallback_carve
    brace_balance_recovery = fm.brace_balance_recovery
    extract_fields = fm.extract_fields_from_object
    HAS_FM = True
    print("[OK] Loaded forensic_main.py helpers (Snappy decompression available)")
except Exception as e:
    HAS_FM = False
    print(f"[WARN] Could not load forensic_main: {e}")
    try_snappy = lambda x: []
    fallback_carve = lambda x: []

# ── Also try plain python-snappy if available ──────────────────────────────────
try:
    import snappy as _snappy
    def try_snappy(raw):
        results = []
        # Try full-file decompress
        try:
            results.append(_snappy.decompress(raw))
        except: pass
        # Try sliding window on 64KB chunks
        chunk = 65536
        for i in range(0, min(len(raw), 4*1024*1024), chunk//2):
            try:
                results.append(_snappy.decompress(raw[i:i+chunk]))
            except: pass
        return results
    print("[OK] python-snappy available")
except: pass

UUID_RE   = re.compile(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
TITLE_RE  = re.compile(rb'"title"\s*:\s*"((?:[^"\\]|\\.){1,300})"')
UPDATE_RE = re.compile(rb'"update_time"\s*:\s*([\d.]+)')
CREATE_RE = re.compile(rb'"create_time"\s*:\s*([\d.]+)')
SNIP_RE   = re.compile(rb'"snippet"\s*:\s*"((?:[^"\\]|\\.){1,500})"')

def decode_json_str(b):
    try: return json.loads(b'"' + b + b'"')
    except: return b.decode('utf-8', errors='replace')

def carve_buffer(buf, source):
    """Carve a raw bytes buffer for conversation titles/IDs."""
    results = []
    for tm in TITLE_RE.finditer(buf):
        title = decode_json_str(tm.group(1))
        if not title or len(title) < 2 or title.startswith('{'):
            continue
        win_s = max(0, tm.start() - 3000)
        win_e = min(len(buf), tm.end() + 3000)
        win   = buf[win_s:win_e]
        uuid_m = UUID_RE.search(win)
        cid = uuid_m.group(1).decode('ascii').lower() if uuid_m else ""
        upd_m = UPDATE_RE.search(win)
        ut = float(upd_m.group(1)) if upd_m else 0.0
        cre_m = CREATE_RE.search(win)
        ct = float(cre_m.group(1)) if cre_m else 0.0
        sn_m = SNIP_RE.search(win)
        snip = decode_json_str(sn_m.group(1)) if sn_m else ""
        results.append({
            "conversation_id": cid,
            "title": title,
            "update_time": ut,
            "create_time": ct,
            "snippet": snip,
            "source": source,
        })
    return results

def scan_dir(directory, label):
    print(f"\n[SCAN] {label}: {directory}")
    if not os.path.isdir(directory):
        print("  [MISS] Directory not found")
        return []
    
    files = (
        sorted(glob.glob(os.path.join(directory, "*.log"))) +
        sorted(glob.glob(os.path.join(directory, "*.ldb")))
    )
    print(f"  Files: {len(files)}")
    
    all_hits = []
    for fpath in files:
        fname = os.path.basename(fpath)
        fsize = os.path.getsize(fpath)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        
        try:
            tmp = os.path.join(BASE, f"_tmp_scan_{os.getpid()}.bin")
            shutil.copy2(fpath, tmp)
            with open(tmp, "rb") as f:
                raw = f.read()
            os.remove(tmp)
        except Exception as e:
            print(f"  [SKIP] {fname}: {e}")
            continue
        
        buffers = [raw]
        
        # Add Snappy-decompressed variants
        try:
            buffers.extend(try_snappy(raw))
        except: pass
        
        hits = []
        for buf in buffers:
            hits.extend(carve_buffer(buf, fname))
        
        # Also use fallback_carve from forensic_main if available
        if HAS_FM:
            try:
                for buf in buffers:
                    carved = fallback_carve(buf)
                    for r in carved:
                        if r.get("title") and len(r.get("title","")) > 1:
                            hits.append({
                                "conversation_id": r.get("conversation_id",""),
                                "title": r.get("title",""),
                                "update_time": r.get("update_time", 0.0),
                                "create_time": r.get("create_time", 0.0),
                                "snippet": r.get("snippet","") or r.get("text",""),
                                "source": fname,
                            })
            except: pass
        
        print(f"  {fname} ({fsize//1024}KB, {mtime}): {len(hits)} hits")
        all_hits.extend(hits)
    
    return all_hits

# Scan both live dirs
hits_idb = scan_dir(LIVE_IDB, "IndexedDB")
hits_ls  = scan_dir(LIVE_LS,  "Local Storage leveldb")

all_hits = hits_idb + hits_ls
print(f"\n[TOTAL] Raw hits: {len(all_hits)}")

# Deduplicate by CID, keep highest update_time
by_cid = {}
for h in all_hits:
    cid = h.get("conversation_id","")
    if not cid:
        continue
    ut = float(h.get("update_time") or 0)
    if cid not in by_cid or ut > float(by_cid[cid].get("update_time") or 0):
        by_cid[cid] = h

print(f"[TOTAL] Unique CIDs: {len(by_cid)}")

# March 2026 threshold
march1_ts = 1772323200.0
feb17_ts  = 1771286400.0
march_hits = {cid: h for cid, h in by_cid.items() if float(h.get("update_time") or 0) >= feb17_ts}
print(f"[TOTAL] Feb 17+ CIDs: {len(march_hits)}")
for cid, h in sorted(march_hits.items(), key=lambda x: x[1]['update_time'], reverse=True)[:20]:
    print(f"  {datetime.fromtimestamp(h['update_time'], tz=timezone.utc).strftime('%Y-%m-%d')} | {h['title']}")

# ── Load existing history & merge ─────────────────────────────────────────────
with open(OUT_HISTORY, encoding='utf-8') as f:
    existing_data = json.load(f)
existing_items = existing_data.get("items", [])

existing_cids = {i.get("conversation_id",""): float(i.get("update_time") or 0)
                 for i in existing_items}

def ts_iso(ts):
    try:
        t = float(ts)
        if t <= 0: return ""
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("updated=%Y-%m-%dT%H:%M:%S.%fZ")
    except: return ""

added = 0
updated = 0
for cid, h in by_cid.items():
    title = h.get("title","")
    ut    = float(h.get("update_time") or 0)
    snip  = h.get("snippet","")
    src   = f"live_ldb/{h.get('source','')}"
    
    if cid not in existing_cids:
        # Add new
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
                "snippet":    snip if snip else f"[No cached content] {ts_iso(ut)}",
                "role":       "assistant" if snip else "",
            },
            "source_file": src,
        }
        existing_items.append(new_item)
        added += 1
    else:
        # Update if newer
        if ut > existing_cids[cid] + 60:
            for item in existing_items:
                if item.get("conversation_id") == cid:
                    item["update_time"] = ut
                    if snip and not snip.startswith('['):
                        item["payload"]["snippet"] = snip
                    updated += 1
                    break

print(f"\n[MERGE] Added: {added} | Updated: {updated}")

# Re-sort
existing_items.sort(key=lambda x: float(x.get("update_time") or 0), reverse=True)

output = {
    "_forensic_notes": existing_data.get("_forensic_notes",""),
    "_recovery_additions": f"Live LDB re-scan 2026-03-19: added {added}, updated {updated}.",
    "items": existing_items,
}
with open(OUT_HISTORY, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"[DONE] {OUT_HISTORY}: {len(existing_items)} total")

"""
dump_ls_keys.py  –  Dump raw Local Storage and IndexedDB LDB content to understand
the key-value structure and find March conversation titles/timestamps.
"""
import os, sys, io, json, re, shutil, struct
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE    = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
APPDATA = os.getenv("LOCALAPPDATA", "")

# Import forensic helpers
sys.path.insert(0, BASE)
import forensic_main as fm

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

# Pattern to find update_time anywhere near a UUID
UUID_BYTES = re.compile(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
# Larger timestamp window - check for floats >= 1771286400 (Feb 17 2026)
# In hex: 1771286400 = 0x69A3BA00
FLOAT_TS_RE = re.compile(rb'(17[67][0-9]{7,8}\.?[0-9]{0,6})')

feb17_ts = 1771286400.0

def scan_file_deep(fpath, label):
    try:
        tmp = fpath + "_tmp_scan"
        shutil.copy2(fpath, tmp)
        with open(tmp, "rb") as f:
            raw = f.read()
        os.remove(tmp)
    except Exception as e:
        print(f"  [ERR] {e}")
        return []
    
    results = []
    
    # Try snappy decompression
    buffers = [raw]
    try:
        buffers.extend(fm.try_snappy_decompress(raw))
    except: pass
    
    for buf in buffers:
        # Decode to text with replacement
        text = buf.decode("utf-8", errors="replace")
        
        # Find all timestamp-like floats near UUIDs
        for m in FLOAT_TS_RE.finditer(buf):
            try:
                ts_val = float(m.group(1))
                if ts_val < feb17_ts:
                    continue
                # Look nearby for UUID and title
                win_s = max(0, m.start() - 2000)
                win_e = min(len(buf), m.end() + 2000)
                win   = buf[win_s:win_e]
                win_t = win.decode("utf-8", errors="replace")
                uuid_m = UUID_BYTES.search(win)
                cid = uuid_m.group(1).decode('ascii').lower() if uuid_m else ""
                title_m = re.search(r'"title"\s*:\s*"([^"\\]{2,200})"', win_t)
                title = title_m.group(1) if title_m else ""
                if cid or title:
                    results.append({
                        "ts": ts_val,
                        "ts_human": datetime.fromtimestamp(ts_val, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                        "cid": cid,
                        "title": title,
                        "src": label,
                    })
            except: pass
    
    return results

print("Scanning for Feb 17+ timestamps in live LDB files...")
all_results = []

import glob
for directory, label in [(LIVE_IDB, "IndexedDB"), (LIVE_LS, "LocalStorage")]:
    for fpath in sorted(glob.glob(os.path.join(directory, "*.log")) + 
                        glob.glob(os.path.join(directory, "*.ldb"))):
        fname = os.path.basename(fpath)
        res = scan_file_deep(fpath, f"{label}/{fname}")
        if res:
            print(f"  {fname}: {len(res)} Feb17+ hits")
            all_results.extend(res)
        else:
            print(f"  {fname}: 0 Feb17+ hits")

# Deduplicate and sort
seen = set()
unique = []
for r in sorted(all_results, key=lambda x: x['ts'], reverse=True):
    key = (r['cid'], r.get('title',''))
    if key not in seen:
        seen.add(key)
        unique.append(r)

print(f"\nTotal Feb17+ unique entries: {len(unique)}")
for r in unique[:30]:
    print(f"  {r['ts_human']} | cid={r['cid'][:20] if r['cid'] else 'N/A'} | title={repr(r['title'][:50])}")

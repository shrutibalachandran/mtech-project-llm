"""
debug_ls_deep.py – Deep scan of Local Storage LDB to find all text content
(not just titles). Shows what's actually stored per-conversation entry.
"""
import sys, io, os, glob, re, shutil, struct, json
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

APPDATA = os.getenv("LOCALAPPDATA", "")
LS_DIR  = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "Local Storage", "leveldb"
)

# Focus on the newest + biggest file
TARGET = os.path.join(LS_DIR, "000825.log")
if not os.path.exists(TARGET):
    files = sorted(glob.glob(os.path.join(LS_DIR, "*.log")), key=os.path.getsize, reverse=True)
    TARGET = files[0] if files else ""

print(f"Scanning: {TARGET}")
try:
    tmp = TARGET + "_dbg"
    shutil.copy2(TARGET, tmp)
    with open(tmp, "rb") as f:
        raw = f.read()
    os.remove(tmp)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

print(f"File size: {len(raw)//1024}KB")

# Strategy: show ALL printable text segments > 20 chars grouped by proximity
# Use aggressive join: allow up to 12 binary bytes gap (V8 varints + tags)
def stitch(data, gap=12, min_run=4):
    segs = []
    i, n = 0, len(data)
    while i < n:
        if 0x20 <= data[i] <= 0x7e:
            s = i
            while i < n and 0x20 <= data[i] <= 0x7e:
                i += 1
            if i - s >= min_run:
                segs.append((s, data[s:i]))
        else:
            i += 1

    merged = []
    j = 0
    while j < len(segs):
        pos, seg = segs[j]
        parts = [seg]
        j += 1
        while j < len(segs):
            tail = pos + sum(len(p) for p in parts)
            if segs[j][0] - tail <= gap:
                parts.append(segs[j][1])
                j += 1
            else:
                break
        merged.append(b" ".join(parts).decode("utf-8", errors="replace"))
    return merged

text_runs = stitch(raw, gap=12, min_run=4)
print(f"\nTotal text segments: {len(text_runs)}")
print("\n--- First 200 segments > 15 chars, filtered ---\n")

skip_pats = [
    re.compile(r'^[0-9a-f-]{36}$'),        # bare UUID
    re.compile(r'^https?://'),              # URL
    re.compile(r'^[A-Za-z0-9+/=]{40,}$'),  # base64
    re.compile(r'"[a-z_]+"$'),             # single key
]

count = 0
for run in text_runs:
    run = run.strip()
    if len(run) < 15:
        continue
    skip = False
    for pat in skip_pats:
        if pat.match(run):
            skip = True; break
    if skip:
        continue
    alpha = sum(1 for c in run if c.isalpha())
    if alpha < len(run) * 0.2:
        continue
    print(f"  [{len(run):4d}] {repr(run[:200])}")
    count += 1
    if count >= 100:
        break

print(f"\nShown {count} segments")

# Also try: extract raw key-value from LDB WAL format
print("\n--- WAL record payloads ---")
from ldb_reader import scan_log
kv_count = 0
for k, v in scan_log(TARGET):
    if len(v) > 50:
        text = v.decode("utf-8", errors="replace")
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
        text = re.sub(r'  +', ' ', text).strip()
        if len(text) > 30:
            key_str = k.decode("utf-8", errors="replace").strip()
            print(f"\nKEY: {repr(key_str[:80])}")
            print(f"VAL: {repr(text[:400])}")
            kv_count += 1
            if kv_count >= 20:
                break
print(f"\n{kv_count} WAL records with content")

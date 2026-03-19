"""
debug_idb_v8.py – Inspect IndexedDB files to understand V8 serialization format
and extract readable text from conversation messages.
"""
import sys, io, os, glob, re, shutil, struct, json
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import cramjam

APPDATA = os.getenv("LOCALAPPDATA", "")
IDB_DIR = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "IndexedDB", "https_chatgpt.com_0.indexeddb.leveldb"
)
BLOB_DIR = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "IndexedDB", "https_chatgpt.com_0.indexeddb.blob"
)

# V8 serialized string patterns:
# V8 uses `"<length_varint><utf8_bytes>` for one-byte strings
# and `c"<length_varint><utf16le_bytes>` for two-byte strings
# In practice for ChatGPT IndexedDB, visible text like `text"` marks field names

# Pattern: any printable-ish sequence of 10+ chars, after common V8 field markers
# "text" field content in V8: b'text"\x??"<actual_string>'
V8_TEXT = re.compile(
    rb'(?:text|parts|content|snippet|title|role)'
    rb'["\x01-\x3f]{1,6}'       # V8 length varint or delimiter
    rb'([\x20-\x7e\x80-\xff]{10,2000})'  # actual content bytes
)

# Simpler: just find long printable runs > 30 chars after removing binary
PRINTABLE = re.compile(rb'[\x20-\x7e]{20,}')

# Known ChatGPT message markers in V8 format
TEXT_FIELD  = re.compile(rb'text"([\x20-\x7e\x80-\xbf]{5,}?)(?=[\x00-\x1f"]|$)', re.DOTALL)
PARTS_FIELD = re.compile(rb'parts"[\x00-\x40]{0,4}([\x20-\x7e\x80-\xbf]{5,}?)(?=[\x00-\x1f"]|$)', re.DOTALL)

def clean_text(b: bytes) -> str:
    """Remove binary noise, keep readable text."""
    # Replace non-printable non-whitespace with space
    cleaned = re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', b' ', b)
    text = cleaned.decode('utf-8', errors='replace')
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text).strip()
    return text

files = sorted(glob.glob(os.path.join(IDB_DIR, "*.log"))) + \
        sorted(glob.glob(os.path.join(IDB_DIR, "*.ldb")))
print(f"IndexedDB files: {len(files)}")

for fpath in files:
    fname = os.path.basename(fpath)
    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M')
    try:
        tmp = fpath + "_dbg"
        shutil.copy2(fpath, tmp)
        with open(tmp, "rb") as f:
            raw = f.read()
        os.remove(tmp)
    except Exception as e:
        continue

    # All buffers
    buffers = [raw]
    CHUNK = 65536
    for i in range(0, min(len(raw), 4*1024*1024), CHUNK//4):
        try:
            dec = bytes(cramjam.snappy.decompress(raw[i:i+CHUNK]))
            if len(dec) > 64:
                buffers.append(dec)
        except: pass

    print(f"\n{fname} ({mtime}, {len(raw)//1024}KB, {len(buffers)} buffers):")
    
    # Find printable runs
    all_runs = []
    for buf in buffers:
        for m in PRINTABLE.finditer(buf):
            txt = m.group(0).decode('utf-8', errors='replace').strip()
            if len(txt) >= 20 and not txt.startswith('http') and '"' not in txt[:3]:
                all_runs.append(txt)
    
    # Show first 5 substantial text runs
    seen = set()
    count = 0
    for run in all_runs:
        if run[:50] in seen:
            continue
        seen.add(run[:50])
        if len(run) > 30 and any(c.isalpha() for c in run[:20]):
            print(f"  TEXT: {repr(run[:150])}")
            count += 1
            if count >= 8:
                break

# Also check the blob file directly
print("\n=== IndexedDB Blob file ===")
for root, dirs, bfiles in os.walk(BLOB_DIR):
    for bf in bfiles:
        bpath = os.path.join(root, bf)
        bsize = os.path.getsize(bpath)
        bmtime = datetime.fromtimestamp(os.path.getmtime(bpath)).strftime('%Y-%m-%d %H:%M')
        print(f"\nBlob: {os.path.relpath(bpath, BLOB_DIR)} ({bsize//1024}KB, {bmtime})")
        try:
            with open(bpath, "rb") as f:
                raw = f.read()
        except: continue
        
        # Extract all printable runs > 30 chars
        count = 0
        seen = set()
        for m in PRINTABLE.finditer(raw):
            txt = m.group(0).decode('utf-8', errors='replace').strip()
            if len(txt) >= 30 and txt[:40] not in seen:
                if any(c.isalpha() for c in txt[:20]):
                    seen.add(txt[:40])
                    print(f"  {repr(txt[:200])}")
                    count += 1
                    if count >= 15:
                        break

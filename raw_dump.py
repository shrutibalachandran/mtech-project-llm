"""
raw_dump.py  –  Dump printable strings from the live LDB files to see what format
the March 2026 conversation data is stored in.
"""
import os, sys, io, re, shutil, glob
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

# Look for ISO dates "2026-03" or ms-epoch "177" followed by 10 digits
ISO_DATE_RE  = re.compile(rb'2026-0[1-9]-\d\d')
MS_EPOCH_RE  = re.compile(rb'177[0-9]{10}')  # millisecond timestamps for early 2026
TITLE_RE     = re.compile(rb'"title"\s*:\s*"(.{2,100}?)"')
UUID_RE      = re.compile(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)

print("Scanning for 2026-03 ISO dates and ms-epoch timestamps in Local Storage LDB...")
print()

for fpath in sorted(glob.glob(os.path.join(LIVE_LS, "*.log")) + 
                    glob.glob(os.path.join(LIVE_LS, "*.ldb"))):
    fname = os.path.basename(fpath)
    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
    try:
        tmp = fpath + "_tmp"
        shutil.copy2(fpath, tmp)
        with open(tmp, "rb") as f:
            raw = f.read()
        os.remove(tmp)
    except Exception as e:
        print(f"{fname}: ERROR {e}")
        continue
    
    buffers = [raw]
    try:
        buffers.extend(fm.try_snappy_decompress(raw))
    except: pass
    
    iso_hits = []
    ms_hits  = []
    title_hits = []
    
    for buf in buffers:
        iso_hits  += ISO_DATE_RE.findall(buf)
        ms_hits   += MS_EPOCH_RE.findall(buf)
        title_hits += TITLE_RE.findall(buf)
    
    print(f"{fname} ({mtime}):")
    print(f"  ISO 2026-0x dates: {len(iso_hits)}")
    if iso_hits:
        for h in sorted(set(iso_hits))[:5]:
            print(f"    {h}")
    print(f"  ms-epoch 177xxxxxxxxxx: {len(ms_hits)}")
    if ms_hits:
        uniq = sorted(set(ms_hits))[:5]
        for h in uniq:
            try:
                ts_s = float(h) / 1000.0
                print(f"    {h.decode()} => {datetime.fromtimestamp(ts_s, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}")
            except:
                print(f"    {h}")
    print(f"  title hits: {len(title_hits)}")
    if title_hits:
        for h in title_hits[:3]:
            try:
                print(f"    title={h[:80].decode('utf-8','replace')}")
            except:
                pass
    print()

# Also check the blob file
blob_file = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "IndexedDB", "https_chatgpt.com_0.indexeddb.blob", "7", "00", "4"
)
if os.path.exists(blob_file):
    print(f"Blob file: {blob_file}")
    sz = os.path.getsize(blob_file)
    mtime = datetime.fromtimestamp(os.path.getmtime(blob_file)).strftime("%Y-%m-%d %H:%M")
    print(f"  Size: {sz//1024}KB, mtime: {mtime}")
    try:
        with open(blob_file, "rb") as f:
            raw = f.read(4096)
        # Print printable chars
        printable = re.sub(rb'[^\x20-\x7e\n\r\t]', b' ', raw)
        print(f"  First 500 printable chars:")
        print(printable[:500].decode('ascii','replace'))
    except Exception as e:
        print(f"  Error: {e}")

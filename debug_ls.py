"""debug_ls.py – Inspect Local Storage LDB to understand why 0 conversations extracted."""
import sys, io, os, glob, re, shutil, struct, json
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

import cramjam

APPDATA = os.getenv("LOCALAPPDATA", "")
LS_DIR  = os.path.join(
    APPDATA, "Packages",
    "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
    "LocalCache", "Roaming", "ChatGPT",
    "Local Storage", "leveldb"
)

CID_DOLLAR = re.compile(rb'id"\$([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
UUID_ANY   = re.compile(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
TITLE_ANY  = re.compile(rb'"title"[^"]{0,10}"([^"]{2,200})"')
UPDATE_DBL = re.compile(rb'(?:updateTime|update_time).{0,4}(.{8})')
UPDATE_MS  = re.compile(rb'(177[0-9]{10}|176[0-9]{10})')

files = sorted(glob.glob(os.path.join(LS_DIR, "*.log"))) + \
        sorted(glob.glob(os.path.join(LS_DIR, "*.ldb")))
print(f"Files: {len(files)}")

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
        print(f"{fname}: ERR {e}")
        continue

    buffers = [raw]
    CHUNK = 65536
    for i in range(0, min(len(raw), 4*1024*1024), CHUNK//4):
        try:
            dec = bytes(cramjam.snappy.decompress(raw[i:i+CHUNK]))
            if len(dec) > 64:
                buffers.append(dec)
        except: pass

    dollar_cids = sum(len(CID_DOLLAR.findall(b)) for b in buffers)
    any_uuids   = sum(len(UUID_ANY.findall(b)) for b in buffers)
    titles      = sum(len(TITLE_ANY.findall(b)) for b in buffers)
    dbl_ts      = sum(len(UPDATE_DBL.findall(b)) for b in buffers)
    ms_ts       = sum(len(UPDATE_MS.findall(b)) for b in buffers)

    # Try to decode double timestamps
    dbl_vals = []
    for buf in buffers:
        for m in UPDATE_DBL.finditer(buf):
            try:
                v = struct.unpack("<d", m.group(1)[:8])[0]
                if 1e9 < v < 3e9:
                    dbl_vals.append(v)
            except: pass

    ms_vals = []
    for buf in buffers:
        for m in UPDATE_MS.finditer(buf):
            try:
                v = int(m.group(1)) / 1000
                ms_vals.append(v)
            except: pass

    print(f"\n{fname} ({mtime}, {len(raw)//1024}KB, {len(buffers)} buffers):")
    print(f"  id\"$ CIDs: {dollar_cids}")
    print(f"  any UUIDs: {any_uuids}")
    print(f"  titles   : {titles}")
    print(f"  dbl ts   : {dbl_ts} -> {[datetime.fromtimestamp(v, tz=timezone.utc).strftime('%Y-%m-%d') for v in dbl_vals[:3]]}")
    print(f"  ms ts    : {ms_ts} -> {[datetime.fromtimestamp(v, tz=timezone.utc).strftime('%Y-%m-%d') for v in ms_vals[:3]]}")
    if titles:
        for buf in buffers:
            for m in TITLE_ANY.finditer(buf):
                t = m.group(1).decode('utf-8', errors='replace')
                print(f"    title: {repr(t[:60])}")
            if TITLE_ANY.search(buf):
                break

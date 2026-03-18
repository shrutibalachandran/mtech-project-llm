"""
scan_ldb_snappy.py - Scan LevelDB .ldb files for conversation titles using snappy block extraction
"""
import os, shutil, sys, glob
sys.path.insert(0, '.')
from forensic_main import try_snappy_decompress

try:
    import cramjam
    HAS_CRAMJAM = True
except:
    HAS_CRAMJAM = False

def scan_ldb_snappy_blocks(data):
    """Try snappy decompression on sliding windows to find conversation data."""
    if not HAS_CRAMJAM:
        return []
    results = []
    for start in range(0, min(len(data), 10_000_000), 512):
        for chunk_size in [4096, 8192, 16384, 32768, 65536]:
            chunk = data[start:start+chunk_size]
            if len(chunk) < 512:
                break
            try:
                dec = bytes(cramjam.snappy.decompress_raw(chunk))
                if len(dec) > 200 and (
                    b'conversations_v2' in dec or
                    (b'"title"' in dec and b'"uuid"' in dec) or
                    b'React Tabs' in dec or
                    b'Combobox' in dec
                ):
                    results.append((start, chunk_size, dec))
                    break
            except:
                pass
    return results


roaming = os.environ.get('APPDATA', '')
ls_dir = os.path.join(roaming, 'Claude', 'Local Storage', 'leveldb')
targets = [b'React Tabs', b'Combobox', b'React Tab', b'conversations_v2']

# Also scan the big 000366.ldb from temp_diag_ldb
files_to_scan = sorted(glob.glob(os.path.join(ls_dir, '*.ldb'))) + \
                sorted(glob.glob(os.path.join(ls_dir, '*.log'))) + \
                ['temp_diag_ldb/000366.ldb', 'temp_diag_ldb/000368.ldb', 'temp_diag_ldb/000370.ldb']

for fp in files_to_scan:
    tmp = '_tmp_sst2.bin'
    try:
        shutil.copy2(fp, tmp)
        with open(tmp, 'rb') as f:
            raw = f.read()
        os.remove(tmp)
    except Exception as e:
        continue

    print(f"\n=== {os.path.basename(fp)} ({len(raw):,} bytes) ===")
    
    # 1. Raw search
    for t in targets:
        idx = raw.lower().find(t.lower())
        if idx != -1:
            ctx = raw[max(0, idx-80):idx+300].decode('utf-8', errors='replace')
            print(f"  [RAW] Found {t.decode()!r} at {idx}:")
            print("  ", ctx[:300])

    # 2. Snappy blocks
    blocks = scan_ldb_snappy_blocks(raw)
    print(f"  Snappy blocks with conv data: {len(blocks)}")
    for off, sz, dec in blocks[:5]:
        print(f"  [SNAPPY @{off} sz={sz}] {len(dec)} bytes decompressed:")
        for t in targets:
            idx2 = dec.lower().find(t.lower())
            if idx2 != -1:
                ctx2 = dec[max(0,idx2-80):idx2+300].decode('utf-8', errors='replace')
                print(f"    Found {t.decode()!r}:")
                print("   ", ctx2[:300])

print("\nDone.")

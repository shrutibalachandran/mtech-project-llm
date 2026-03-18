import os
import glob
import zlib
import re

try:
    import brotli
except ImportError:
    brotli = None

def scan_external_files():
    cache_dir = r"c:\Users\sreya\OneDrive\Desktop\project3\cache_tmp"
    files = glob.glob(os.path.join(cache_dir, "f_*"))
    keywords = [b"forensics", b"alphabet", b"njullu", b"conversation_id", b"mapping"]
    
    print(f"Scanning {len(files)} external files...")
    all_hits = []

    for fp in files:
        try:
            with open(fp, "rb") as f:
                raw_data = f.read()
            
            # 1. Raw search
            found_raw = False
            for kw in keywords:
                if kw in raw_data.lower():
                    print(f"File: {os.path.basename(fp)} - Found RAW '{kw.decode()}'")
                    found_raw = True
            
            # 2. Zlib/Gzip check
            decomp = None
            try:
                decomp = zlib.decompress(raw_data, zlib.MAX_WBITS | 32)
            except:
                try:
                    decomp = zlib.decompress(raw_data, -15)
                except:
                    pass
            
            if decomp:
                for kw in keywords:
                    if kw in decomp.lower():
                        print(f"File: {os.path.basename(fp)} - Found ZLIB '{kw.decode()}'")
                        with open(f"recovered_{os.path.basename(fp)}.bin", "wb") as out:
                            out.write(decomp)

            # 3. Brotli check
            if brotli:
                try:
                    decomp = brotli.decompress(raw_data)
                    for kw in keywords:
                        if kw in decomp.lower():
                            print(f"File: {os.path.basename(fp)} - Found BROTLI '{kw.decode()}'")
                            with open(f"recovered_br_{os.path.basename(fp)}.bin", "wb") as out:
                                out.write(decomp)
                except:
                    pass
        except:
            pass

if __name__ == "__main__":
    scan_external_files()

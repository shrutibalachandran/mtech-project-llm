import os
import glob
import re
import zlib

try:
    import brotli
except ImportError:
    brotli = None

def decompress_data(data):
    try: return zlib.decompress(data, zlib.MAX_WBITS | 32)
    except: pass
    try: return zlib.decompress(data, -15)
    except: pass
    if brotli:
        try: return brotli.decompress(data)
        except: pass
    return None

def find_all_http_bodies(data):
    bodies = []
    # Identify bodies following \r\n\r\n
    for match in re.finditer(rb'\r?\n\r?\n', data):
        start = match.end()
        # Take a reasonable chunk or look for next header/end
        bodies.append(data[start:start+1000000]) 
    return bodies

def scan_data_files():
    cache_dir = r"cache_tmp"
    data_files = glob.glob(os.path.join(cache_dir, "data_*"))
    
    count = 0
    print(f"Scanning {len(data_files)} data_* files for compressed HTTP bodies...")
    for fp in data_files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
            
            bodies = find_all_http_bodies(data)
            for i, body in enumerate(bodies):
                decomp = decompress_data(body)
                if decomp and len(decomp) > 100:
                    out_name = f"recovered_{os.path.basename(fp)}_body_{i}.bin"
                    with open(out_name, "wb") as out:
                        out.write(decomp)
                    count += 1
                    
        except Exception as e:
            print(f"Error on {fp}: {e}")
            
    print(f"Successfully extracted {count} compressed payloads from data_* files.")

if __name__ == "__main__":
    scan_data_files()

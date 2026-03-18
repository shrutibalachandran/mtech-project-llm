import os
import zlib
import re
import json

def sweep_decompression(filepath):
    print(f"Sweeping {os.path.basename(filepath)}...")
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except:
        return

    # Scan for Zlib headers (\x78\x01, \x78\x9c, \x78\xda)
    matches = list(re.finditer(rb'\x78[\x01\x9c\xda]', data))
    print(f"Found {len(matches)} potential Zlib headers.")
    
    found_count = 0
    for m in matches:
        start = m.start()
        # Try decompressing chunks of increasing size or until end
        # We'll use a sliding window or just try to decompress as much as possible
        try:
            # decompress() will stop at the end of the stream
            decompressed = zlib.decompress(data[start:])
            if len(decompressed) > 500: # Only care about significant chunks
                # Search for keywords in decompressed data
                keywords = [b"forensics", b"alphabet", b"njullu", b"conversation_id"]
                for kw in keywords:
                    if kw in decompressed.lower():
                        print(f"Found '{kw.decode()}' in decompressed chunk at {start} (Size: {len(decompressed)})")
                        # Save a sample
                        with open(f"decompressed_{start}.bin", "wb") as out:
                            out.write(decompressed)
                        found_count += 1
                        break
        except:
            pass
    print(f"Finished {os.path.basename(filepath)}. Successfully recovered {found_count} candidate chunks.")

if __name__ == "__main__":
    cache_dir = r"c:\Users\sreya\OneDrive\Desktop\project3\cache_tmp"
    sweep_decompression(os.path.join(cache_dir, "data_2"))
    sweep_decompression(os.path.join(cache_dir, "data_3"))

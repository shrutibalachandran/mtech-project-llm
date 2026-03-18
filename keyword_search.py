import os
import glob
import re

def search_keywords():
    cache_dir = r"c:\Users\sreya\OneDrive\Desktop\project3\cache_tmp"
    keywords = [b"forensics", b"alphabet", b"njullu"]
    files = glob.glob(os.path.join(cache_dir, "data_*")) + glob.glob(os.path.join(cache_dir, "f_*"))
    
    for fp in files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
                for kw in keywords:
                    for m in re.finditer(re.escape(kw), data, re.I):
                        start = max(0, m.start() - 200)
                        end = min(len(data), m.end() + 500)
                        context = data[start:end]
                        # Look for strings and hex markers
                        print(f"File: {os.path.basename(fp)} - Found '{kw.decode()}' at {m.start()}")
                        # Print a snippet of the context (cleaned up)
                        snippet = "".join([chr(b) if 32 <= b <= 126 else "." for b in context])
                        print(f"Context: {snippet}\n")
        except:
            pass

if __name__ == "__main__":
    search_keywords()

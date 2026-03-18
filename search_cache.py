import os

cache_dir = r"C:\Users\sreya\AppData\Roaming\Claude\Cache\Cache_Data"
keywords = [b"Deadliest", b"Bat and ball", b"tuberculosis"]

print(f"Searching {cache_dir} for keywords...")

found = False
for root, dirs, files in os.walk(cache_dir):
    for f in files:
        if f.startswith("f_") or f.startswith("data_"):
            path = os.path.join(root, f)
            try:
                with open(path, "rb") as x:
                    data = x.read()
                    for kw in keywords:
                        if kw.lower() in data.lower():
                            print(f"FOUND {kw} in {f}!")
                            idx = data.lower().find(kw.lower())
                            window = data[max(0, idx-50):idx+500]
                            safe = ''.join(chr(b) if 32<=b<127 or b in (9,10,13) else ' ' for b in window)
                            print(f"  Preview: {safe.strip()}")
                            found = True
            except Exception as e:
                pass

if not found:
    print("Zero matches found in the entire cache.")

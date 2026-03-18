import os
import re
import json

def brace_balance(data, start):
    depth = 0
    in_str = False
    esc = False
    for i in range(start, min(len(data), start + 200000)):
        b = data[i:i+1]
        if in_str:
            if b == b'"' and not esc: in_str = False
            elif b == b'\\' and not esc: esc = True
            else: esc = False
        else:
            if b == b'"': in_str = True
            elif b == b'{': depth += 1
            elif b == b'}':
                depth -= 1
                if depth == 0:
                    return data[start:i+1]
    return None

def deep_carve():
    fp = r"c:\Users\sreya\OneDrive\Desktop\project3\cache_tmp\data_1"
    with open(fp, "rb") as f:
        data = f.read()
    
    uuids = [b"6977b057-1ae8-8324-a696-b4f3ffe786ca", b"69830941-c3d8-8323-a901-aba6df957866"]
    found = []
    
    for u in uuids:
        print(f"Searching for {u.decode()}...")
        for m in re.finditer(u, data):
            # Look backwards for a { up to 5000 bytes
            for i in range(m.start(), max(0, m.start() - 5000), -1):
                if data[i:i+1] == b'{':
                    obj = brace_balance(data, i)
                    if obj and u in obj:
                        try:
                            # Try to decode and check if it has content
                            text = obj.decode('utf-8', errors='ignore')
                            if "title" in text or "content" in text:
                                found.append(text)
                                print(f"  Captured object at {i}")
                                break
                        except: pass
    
    with open(r"c:\Users\sreya\OneDrive\Desktop\project3\target_fragments.json", "w", encoding="utf-8") as out:
        json.dump(list(set(found)), out, indent=2)
    print(f"Total targeted fragments found: {len(set(found))}")

if __name__ == "__main__":
    deep_carve()

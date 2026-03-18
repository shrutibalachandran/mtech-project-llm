import os
import glob
import re
import json

def search_keywords():
    cache_dir = r"c:\Users\sreya\OneDrive\Desktop\project3\cache_tmp"
    # Added common chat markers
    keywords = [b"njullu", b"alphabet", b"forensics", b"6977b057", b"69830941"]
    files = glob.glob(os.path.join(cache_dir, "data_*")) + glob.glob(os.path.join(cache_dir, "f_*"))
    
    results = []
    
    for fp in files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
                for kw in keywords:
                    for m in re.finditer(re.escape(kw), data, re.I):
                        start = max(0, m.start() - 300)
                        end = min(len(data), m.end() + 1000)
                        context = data[start:end]
                        
                        # Try to find JSON boundaries
                        # Look for '{' before and '}' after
                        match_text = context.decode('utf-8', errors='ignore')
                        # Simple heuristic to grab the surrounding object
                        res = {
                            "file": os.path.basename(fp),
                            "keyword": kw.decode(),
                            "offset": m.start(),
                            "snippet": match_text[200:400] # Just for logging
                        }
                        
                        # Attempt to carve JSON
                        brace_count = 0
                        json_start = -1
                        for i in range(m.start(), max(0, m.start() - 2000), -1):
                            if data[i:i+1] == b'{':
                                json_start = i
                                break
                        
                        if json_start != -1:
                            depth = 0
                            for i in range(json_start, min(len(data), json_start + 5000)):
                                if data[i:i+1] == b'{': depth += 1
                                elif data[i:i+1] == b'}':
                                    depth -= 1
                                    if depth == 0:
                                        try:
                                            obj_str = data[json_start:i+1].decode('utf-8', errors='ignore')
                                            # Validate if it looks like ChatGPT data
                                            if "conversation_id" in obj_str or "title" in obj_str or "text" in obj_str:
                                                results.append(obj_str)
                                                break
                                        except: pass
        except:
            pass
            
    # Deduplicate and save unique fragments to a dedicated file
    unique_frags = list(set(results))
    with open(r"c:\Users\sreya\OneDrive\Desktop\project3\manual_fragments.json", "w", encoding="utf-8") as out:
        json.dump(unique_frags, out, indent=2)
    
    print(f"Extracted {len(unique_frags)} unique fragments to manual_fragments.json")

if __name__ == "__main__":
    search_keywords()

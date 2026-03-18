import json
import os
from datetime import datetime

def extract_all_conversations(obj):
    results = []
    def walk(node):
        if isinstance(node, dict):
            text, role, ts = "", "", None
            # Content
            for k in ['content', 'message', 'text', 'body', 'parts', 'p']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): text = val
                    elif isinstance(val, list): text = "\n".join([str(p) for p in val if isinstance(p, str)])
                    elif isinstance(val, dict):
                        p = val.get('parts', [])
                        if isinstance(p, list): text = "\n".join([str(x) for x in p if isinstance(x, str)])
                        elif 'text' in val: text = val['text']
            # Role
            for k in ['author', 'role', 'user_role', 'sender', 'name']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): role = val
                    elif isinstance(val, dict) and 'role' in val: role = val['role']
            # Time
            for k in ['create_time', 'updated_at', 'timestamp', 'time', 'created_at', 'mtime']:
                if k in node:
                    try:
                        v = float(node[k])
                        if v > 1e12: v /= 1000.0
                        if 1.5e9 < v < 2e9: ts = v
                    except: pass
            
            if text and (role or ts):
                role_label = role.upper() if role else "FRAGMENT"
                ts_val = ts if ts else 0
                results.append({
                    'raw_ts': ts_val, 
                    'time': datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "UNKNOWN", 
                    'role': role_label, 
                    'text': text.strip()
                })
            for v in node.values(): walk(v)
        elif isinstance(node, list):
            for i in node: walk(i)
    walk(obj)
    return results

def inspect_targets():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    targets = ['recovered_br_f_000069.bin', 'recovered_br_f_00023f.bin']
    
    for fp in targets:
        print(f"\n==========================================")
        print(f"FILE: {fp}")
        print(f"==========================================")
        try:
            with open(fp, "rb") as f:
                data = f.read()
            obj = json.loads(data)
            
            # Print title if exists
            if 'title' in obj:
                print(f"TITLE: {obj['title']}")
                
            entries = extract_all_conversations(obj)
            # Deduplicate entries by text
            seen_text = set()
            for e in entries:
                if e['text'] not in seen_text:
                    print(f"[{e['time']}] {e['role']}:")
                    print(f"{e['text']}")
                    print("-" * 20)
                    seen_text.add(e['text'])
        except Exception as e:
            print(f"Error inspecting {fp}: {e}")

if __name__ == "__main__":
    inspect_targets()

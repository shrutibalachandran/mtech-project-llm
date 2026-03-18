import os
import json
import glob
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

def finalize_report():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    recovered_files = glob.glob("recovered_*.bin")
    
    all_entries = []
    seen = set()
    
    print(f"Finalizing report from {len(recovered_files)} recovered files...")
    
    for fp in recovered_files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
            # Most are JSON
            try:
                obj = json.loads(data)
                entries = extract_all_conversations(obj)
                for e in entries:
                    key = hash((e['time'], e['role'], e['text'][:300]))
                    if key not in seen:
                        seen.add(key)
                        all_entries.append(e)
            except:
                # If not JSON, it might be a fragment or V8
                # For now we focus on the successful JSON ones
                pass
        except:
            pass

    # Sort Newest to Oldest
    all_entries.sort(key=lambda x: x['raw_ts'], reverse=True)
    
    output_path = "final_cache_forensic_report.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# ChatGPT Recovered Conversation Report\n")
        f.write(f"*Generated: {datetime.now()}*\n")
        f.write(f"*Total Unique Messages Recovered: {len(all_entries)}*\n\n")
        
        # High-priority topics section (if found)
        keywords = ["forensics", "alphabet", "njullu"]
        found_topics = {kw: [] for kw in keywords}
        
        for e in all_entries:
            for kw in keywords:
                if kw in e['text'].lower():
                    found_topics[kw].append(e)
        
        f.write("## 🎯 Target Topics Recovered\n\n")
        for kw, items in found_topics.items():
            if items:
                f.write(f"### Topic: {kw.capitalize()}\n")
                for item in items:
                    f.write(f"**[{item['time']}] {item['role']}**\n{item['text']}\n\n")
                f.write("---\n\n")
            else:
                f.write(f"### Topic: {kw.capitalize()}\n*(No direct message matches found in current recovered set, though search history was present)*\n\n")

        f.write("## 📂 Full Timeline (Newest to Oldest)\n\n")
        for e in all_entries:
            f.write(f"### [{e['time']}] {e['role']}\n{e['text']}\n\n---\n\n")

    print(f"Final report written to {output_path}. Recovered {len(all_entries)} entries.")

if __name__ == "__main__":
    finalize_report()

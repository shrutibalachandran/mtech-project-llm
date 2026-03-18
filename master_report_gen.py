import os
import json
import glob
import re
from datetime import datetime

def extract_all_possible_messages(obj):
    """Aggressively extracts anything resembling a message from a JSON object with context propagation."""
    results = []
    
    def walk(node, ctx_title=None, ctx_ts=None):
        if isinstance(node, dict):
            # Update context
            new_title = node.get('title') or ctx_title
            
            # Timestamp discovery
            new_ts = ctx_ts
            for k in ['update_time', 'create_time', 'updated_at', 'timestamp', 'time', 'created_at']:
                if k in node:
                    try:
                        v = float(node[k])
                        if v > 1e12: v /= 1000.0
                        if 1.5e9 < v < 2e9: 
                            new_ts = v
                            break 
                    except: pass
            
            # Content discovery
            text = ""
            for k in ['content', 'message', 'text', 'body', 'parts', 'p', 'snippet']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): text = val
                    elif isinstance(val, list): text = "\n".join([str(p) for p in val if isinstance(p, str)])
                    elif isinstance(val, dict):
                        p = val.get('parts', [])
                        if isinstance(p, list): text = "\n".join([str(x) for x in p if isinstance(x, str)])
                        elif 'text' in val: text = val['text']
            
            # Role discovery
            role = ""
            for k in ['author', 'role', 'user_role', 'sender', 'name']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): role = val
                    elif isinstance(val, dict) and 'role' in val: role = val['role']
            
            if text and text.strip():
                role_label = role.upper() if role else "MESSAGE"
                ts_val = new_ts if new_ts else 0
                results.append({
                    'raw_ts': ts_val,
                    'time': datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "UNKNOWN",
                    'role': role_label,
                    'text': text.strip(),
                    'title': new_title
                })
            
            # Recurse
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v, new_title, new_ts)
                
        elif isinstance(node, list):
            for i in node:
                walk(i, ctx_title, ctx_ts)

    walk(obj)
    return results

def fast_json_extract(data):
    """Finds and parses all JSON objects in a binary blob efficiently."""
    objs = []
    # Find all { starts
    for match in re.finditer(rb'\{', data):
        start = match.start()
        # Fast scan for matching }
        depth = 0
        for i in range(start, min(start + 500000, len(data))):
            if data[i:i+1] == b'{': depth += 1
            elif data[i:i+1] == b'}':
                depth -= 1
                if depth == 0:
                    try:
                        chunk = data[start:i+1]
                        # Quick filter: must contain some keywords normally in messages
                        if b'role' in chunk or b'text' in chunk or b'snippet' in chunk or b'mapping' in chunk:
                            objs.append(json.loads(chunk))
                    except: pass
                    break
    return objs

def produce_master_report():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    files = glob.glob("recovered_*.bin")
    
    all_messages = []
    seen = set()
    
    print(f"Aggregating data from {len(files)} recovered files...")
    
    for fp in files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
            # Try parsing whole file first
            try:
                obj = json.loads(data)
                found = extract_all_possible_messages(obj)
                for m in found:
                    if len(m['text']) < 5 and m['role'] == "MESSAGE": continue
                    key = (m['time'], m['role'], m['text'][:1000])
                    if key not in seen:
                        seen.add(key)
                        all_messages.append(m)
            except:
                # Use fast extractor for chunks
                objs = fast_json_extract(data)
                for obj in objs:
                    found = extract_all_possible_messages(obj)
                    for m in found:
                        if len(m['text']) < 5 and m['role'] == "MESSAGE": continue
                        key = (m['time'], m['role'], m['text'][:1000])
                        if key not in seen:
                            seen.add(key)
                            all_messages.append(m)
        except: pass
    
    # Scan data_1 for search history
    try:
        d1 = r"cache_tmp\data_1"
        if os.path.exists(d1):
            with open(d1, "rb") as f:
                d = f.read()
            for m in re.finditer(rb'query=([^&\s\x00]+)', d):
                try:
                    query = m.group(1).decode('utf-8', errors='replace').replace('+', ' ')
                    all_messages.append({
                        'raw_ts': 1773155000, 
                        'time': "2026-03-11 (RECENT)",
                        'role': "SEARCH_INTENT",
                        'text': f"User Search Request: {query}",
                        'title': "Search History"
                    })
                except: pass
    except: pass

    # Sort: Newest to Oldest
    all_messages.sort(key=lambda x: x['raw_ts'], reverse=True)
    
    output_path = "FULL_CHRONOLOGICAL_CHAT_RECOVERY.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# ENTIRE CHAT RECOVERY (Chronological Order)\n")
        f.write(f"*Total Unique Records: {len(all_messages)}*\n")
        f.write(f"*Report Generated: {datetime.now()}*\n\n")
        
        current_date = None
        for m in all_messages:
            msg_date = m['time'].split(' ')[0]
            if msg_date != current_date:
                f.write(f"\n## 📅 {msg_date}\n\n")
                current_date = msg_date
            
            title_str = f" | **Title:** {m['title']}" if m['title'] else ""
            f.write(f"### [{m['time']}] {m['role']}{title_str}\n")
            f.write(f"{m['text']}\n\n")
            f.write("---\n\n")

    print(f"Done. Report written to {output_path}. Total records: {len(all_messages)}")

if __name__ == "__main__":
    produce_master_report()

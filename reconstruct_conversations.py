import glob
import os
import json
from datetime import datetime

def extract_all_conversations(obj):
    results = []
    def walk(node):
        if isinstance(node, dict):
            text, role, ts = "", "", None
            for k in ['content', 'message', 'text', 'body', 'parts', 'p']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): text = val
                    elif isinstance(val, list): text = "\n".join([str(p) for p in val if isinstance(p, str)])
                    elif isinstance(val, dict):
                        p = val.get('parts', [])
                        if isinstance(p, list): text = "\n".join([str(x) for x in p if isinstance(x, str)])
                        elif 'text' in val: text = val['text']
            for k in ['author', 'role', 'user_role', 'sender', 'name']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): role = val
                    elif isinstance(val, dict) and 'role' in val: role = val['role']
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
                results.append({'raw_ts': ts_val, 'time': datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "UNKNOWN", 'role': role_label, 'text': text.strip()})
            for v in node.values(): walk(v)
        elif isinstance(node, list):
            for i in node: walk(i)
    walk(obj)
    return results

def find_conversations():
    files = glob.glob('recovered_*.bin')
    all_conversations = []
    
    for fp in files:
        try:
            with open(fp, 'rb') as f:
                data = f.read()
            if b'"mapping":' in data or b'{"mapping":' in data:
                obj = json.loads(data)
                title = obj.get('title', 'Unknown')
                entries = extract_all_conversations(obj)
                if entries:
                    all_conversations.append({'title': title, 'entries': entries, 'file': fp})
        except:
            pass
            
    # Sort conversations by the latest message time
    all_conversations.sort(key=lambda x: max([e['raw_ts'] for e in x['entries']], default=0), reverse=True)
    
    with open("recovered_conversations_full.md", "w", encoding="utf-8") as f:
        f.write("# Reconstructed ChatGPT Conversations from Cache\n\n")
        for conv in all_conversations:
            f.write(f"## {conv['title']} (File: {conv['file']})\n")
            seen_text = set()
            for e in conv['entries']:
                if e['text'] not in seen_text:
                    f.write(f"**[{e['time']}] {e['role']}**\n{e['text']}\n\n")
                    seen_text.add(e['text'])
            f.write("---\n\n")
            
    print(f"Summary: Reconstructed {len(all_conversations)} conversations into recovered_conversations_full.md")

if __name__ == "__main__":
    find_conversations()

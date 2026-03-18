import json
import glob
import os
from datetime import datetime

def extract_metadata():
    files = glob.glob('recovered_*.bin')
    all_snippets = []
    seen = set()
    
    for fp in files:
        try:
            with open(fp, 'rb') as f:
                data = f.read()
            obj = json.loads(data)
            
            # Case 1: List of items
            if isinstance(obj, dict) and 'items' in obj:
                for item in obj['items']:
                    title = item.get('title', 'No Title')
                    snippet = item.get('snippet', '')
                    cid = item.get('conversation_id', '')
                    ts = item.get('update_time', 0)
                    if snippet and (cid, snippet[:100]) not in seen:
                        all_snippets.append({
                            'title': title, 
                            'snippet': snippet, 
                            'id': cid, 
                            'ts': ts,
                            'time': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "UNKNOWN"
                        })
                        seen.add((cid, snippet[:100]))
            
            # Case 2: Single item
            elif isinstance(obj, dict) and 'snippet' in obj:
                title = obj.get('title', 'No Title')
                snippet = obj.get('snippet', '')
                cid = obj.get('conversation_id', '')
                ts = obj.get('update_time', 0)
                if snippet and (cid, snippet[:100]) not in seen:
                    all_snippets.append({
                        'title': title, 
                        'snippet': snippet, 
                        'id': cid, 
                        'ts': ts,
                        'time': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "UNKNOWN"
                    })
                    seen.add((cid, snippet[:100]))
        except:
            pass
            
    # Sort by time
    all_snippets.sort(key=lambda x: x['ts'], reverse=True)
    
    with open("recovered_snippets.md", "w", encoding="utf-8") as f:
        f.write("# Recovered Conversation Snippets\n\n")
        for s in all_snippets:
            f.write(f"## {s['title']} ({s['time']})\n")
            f.write(f"**ID:** {s['id']}\n\n")
            f.write(f"{s['snippet']}\n\n---\n\n")
            
    # Highlight targets
    targets = ["forensics", "alphabet", "njullu"]
    print(f"Found {len(all_snippets)} unique snippets.")
    for s in all_snippets:
        for t in targets:
            if t in s['title'].lower() or t in s['snippet'].lower():
                print(f"TARGET MATCH: {t.upper()} in '{s['title']}' at {s['time']}")

if __name__ == "__main__":
    extract_metadata()

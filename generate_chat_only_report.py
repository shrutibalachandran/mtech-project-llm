import os
import json
import glob
import re
import hashlib
from datetime import datetime
from generate_json_report import extract_all_messages, normalize_text

def produce_chat_only_report():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    files = glob.glob("recovered_*.bin")
    
    raw_messages = []
    print(f"Collecting chat messages from {len(files)} fragments...")
    
    for fp in files:
        try:
            with open(fp, "rb") as f:
                data = f.read()
            try:
                obj = json.loads(data)
                # Filter for non-search
                if isinstance(obj, dict) and obj.get('conversation_id') == 'search_history': continue
                raw_messages.extend(extract_all_messages(obj))
            except: pass
        except: pass

    # Global Deduplication
    seen_hashes = set()
    unique_messages = []
    for m in raw_messages:
        if m['cid'] == 'search_history': continue
        norm = normalize_text(m['text'])
        h = hashlib.md5(norm[:512].encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique_messages.append(m)

    # Global Sorting: CID, then TS, then Role (User first)
    def role_sort_key(r):
        r = str(r).lower()
        if 'user' in r: return 0
        if 'assistant' in r: return 1
        return 2

    unique_messages.sort(key=lambda x: (x['cid'], x['ts'], role_sort_key(x['role'])))

    # Global Pairing
    final_items = []
    i = 0
    while i < len(unique_messages):
        m = unique_messages[i]
        paired = False
        if i + 1 < len(unique_messages):
            next_m = unique_messages[i+1]
            if next_m['cid'] == m['cid'] and next_m['cid'] != 'unknown_cid':
                m_is_user = 'user' in m['role'] or (m['role'] == 'unknown' and '?' in m['text'])
                n_is_ai = 'assistant' in next_m['role'] or (next_m['role'] == 'unknown' and len(next_m['text']) > len(m['text'])*2)
                
                # Also allow User -> User if they are very close in time? No, that's usually just fragmented mess.
                if m_is_user and n_is_ai:
                    final_items.append({
                        "conversation_id": m['cid'],
                        "current_node_id": next_m['id'],
                        "title": next_m['title'] if next_m['title'] != 'Untitled Conversation' else m['title'],
                        "update_time": next_m['ts'] or m['ts'],
                        "payload": {
                            "kind": "interaction",
                            "user_query": m['text'],
                            "ai_response": next_m['text'],
                            "snippet": f"USER: {m['text']}\n\nAI: {next_m['text']}"
                        }
                    })
                    i += 2
                    paired = True

        if not paired:
            final_items.append({
                "conversation_id": m['cid'],
                "current_node_id": m['id'],
                "title": m['title'],
                "update_time": m['ts'],
                "payload": {
                    "kind": "message",
                    "role": m['role'],
                    "snippet": m['text']
                }
            })
            i+1
            i += 1

    # Decode timestamps and Final Sort strictly Newest -> Oldest
    for it in final_items:
        ts = it.get('update_time', 0)
        it['update_time_decoded'] = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "UNKNOWN"

    final_items.sort(key=lambda x: x['update_time'], reverse=True)
    
    output_path = "RECOVERED_CHAT_ONLY.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"items": final_items}, f, indent=2, ensure_ascii=False)

    print(f"Success. Chat-only report written to {output_path}.")
    print(f"Total Unique Conversations: {len(final_items)}")

if __name__ == "__main__":
    produce_chat_only_report()

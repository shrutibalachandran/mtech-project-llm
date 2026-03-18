import os
import json
import glob
import re
import hashlib
from datetime import datetime

def normalize_text(text):
    """Normalize text for deduplication: remove whitespace, lowered."""
    if not text: return ""
    return re.sub(r'\s+', '', text).lower()

def extract_all_messages(obj):
    """
    Universally extracts all messages from any JSON structure without pairing yet.
    """
    messages = []
    
    def get_text_from_node(node):
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
        return text.strip()

    def get_role_from_node(node):
        role = ""
        for k in ['author', 'role', 'user_role', 'sender', 'name']:
            if k in node:
                val = node[k]
                if isinstance(val, str): role = val
                elif isinstance(val, dict) and 'role' in val: role = val['role']
                if role: break
        
        if not role or role.lower() == 'unknown':
            txt = get_text_from_node(node).lower()
            if not txt: return "unknown"
            ai_hints = ["here's", "certainly", "i can", "is a", "```", "###", "**"]
            user_hints = ["can you", "explain", "how to", "what is", "help", "?"]
            ascore = sum(1 for h in ai_hints if h in txt)
            uscore = sum(1 for h in user_hints if h in txt)
            if "```" in txt or "###" in txt: ascore += 5
            if txt.endswith("?"): uscore += 3
            if ascore > uscore: role = "assistant"
            elif uscore > ascore: role = "user"
        return str(role).lower()

    def get_ts_from_node(node):
        for k in ['update_time', 'create_time', 'updated_at', 'timestamp', 'time', 'created_at']:
            if k in node:
                try:
                    v = float(node[k])
                    if v > 1e12: v /= 1000.0
                    if 1.5e9 < v < 2e9: return v
                except: pass
        return None

    global_cid = obj.get('conversation_id', 'unknown_cid') if isinstance(obj, dict) else 'unknown_cid'
    global_title = obj.get('title', 'Untitled Conversation') if isinstance(obj, dict) else 'Untitled Conversation'

    def find_uuid(text):
        m = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', str(text), re.I)
        return m.group(1) if m else None

    def find_title(text):
        m = re.search(r'["\']title["\']\s*:\s*["\'](.*?)["\']', str(text), re.I)
        if not m:
            m = re.search(r'["\']tle["\']\s*:\s*["\'](.*?)["\']', str(text), re.I)
        return m.group(1) if m else None

    def walk(node, ctx_title=None, ctx_ts=None, ctx_cid=None, ctx_role=None):
        if isinstance(node, dict):
            # Skip objects that are explicitly metadata for titles or search
            if node.get('kind') in ['title', 'search']:
                return

            new_title = node.get('title') or find_title(str(node)) or ctx_title
            new_cid = node.get('conversation_id') or find_uuid(str(node)) or ctx_cid
            new_ts = get_ts_from_node(node) or ctx_ts
            local_role = get_role_from_node(node)
            new_role = (local_role if local_role != 'unknown' else None) or ctx_role
            
            txt = get_text_from_node(node)
            if txt:
                # Deduplication: If the 'message' text is exactly the title, 
                # and it's short, it's likely just a title record. Skip it.
                if txt == new_title or txt == global_title:
                    if len(txt) < 100: # Real messages can occasionally start like the title, but title-records are short
                        pass 
                    else:
                        messages.append({
                            'id': node.get('id') or node.get('message_id') or find_uuid(str(node)) or 'unknown',
                            'text': txt,
                            'role': new_role or 'unknown',
                            'ts': new_ts or ctx_ts or 0,
                            'cid': new_cid or ctx_cid or 'unknown_cid',
                            'title': new_title or ctx_title or 'Untitled Conversation'
                        })
                else:
                    messages.append({
                        'id': node.get('id') or node.get('message_id') or find_uuid(str(node)) or 'unknown',
                        'text': txt,
                        'role': new_role or 'unknown',
                        'ts': new_ts or ctx_ts or 0,
                        'cid': new_cid or ctx_cid or 'unknown_cid',
                        'title': new_title or ctx_title or 'Untitled Conversation'
                    })
                
                # If we found a substantial message, stop recursing into its children to avoid duplicate snippets
                if len(txt) > 50: return 

            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    if k in ['author', 'content', 'metadata']: continue
                    walk(v, new_title, new_ts, new_cid, new_role)
        elif isinstance(node, list):
            for x in node: walk(x, ctx_title, ctx_ts, ctx_cid, ctx_role)

    walk(obj, global_title, None, global_cid)
    return messages

def produce_json_report():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    files = glob.glob("recovered_*.bin")
    
    raw_messages = []
    orphan_items = []
    print(f"Collecting messages from {len(files)} fragments...")
    
    # Add a fallback for malformed JSON
    from forensic_utils import create_orphan_entry, is_conversational
    
    for fp in files:
        app_source = "Claude" if "_claude_" in fp else "ChatGPT"
        try:
            with open(fp, "rb") as f:
                data = f.read()
            try:
                obj = json.loads(data)
                msgs = extract_all_messages(obj)
                for m in msgs: m['app_source'] = app_source
                raw_messages.extend(msgs)
            except json.JSONDecodeError:
                # TIER 2 RECOVERY: Fallback parsing for partial JSON
                raw_text = data.decode('utf-8', errors='ignore')
                if is_conversational(raw_text):
                    orphan = create_orphan_entry(raw_text, {"source_file": fp, "app_source": app_source})
                    orphan['payload']['app'] = app_source
                    orphan_items.append(orphan)
                    print(f"  Recovered orphan fragment from {fp} ({app_source})")
            except: pass
        except: pass

    # Global Deduplication
    seen_hashes = set()
    unique_messages = []
    for m in raw_messages:
        norm = normalize_text(m['text'])
        h = hashlib.md5(norm[:512].encode()).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique_messages.append(m)

    # Global Sorting
    unique_messages.sort(key=lambda x: (x['cid'], x['ts']))

    # Global Pairing
    all_items = []
    all_items.extend(orphan_items)
    i = 0
    while i < len(unique_messages):
        m = unique_messages[i]
        paired = False
        if i + 1 < len(unique_messages):
            next_m = unique_messages[i+1]
            if next_m['cid'] == m['cid'] and next_m['cid'] != 'unknown_cid':
                # Check if it's a User -> Assistant pair
                # Or even if roles are unknown, if they are adjacent in time, pair them
                m_is_user = 'user' in m['role'] or (m['role'] == 'unknown' and '?' in m['text'])
                n_is_ai = 'assistant' in next_m['role'] or (next_m['role'] == 'unknown' and len(next_m['text']) > len(m['text'])*2)
                
                if m_is_user and n_is_ai:
                    all_items.append({
                        "conversation_id": m['cid'],
                        "current_node_id": next_m['id'],
                        "title": next_m['title'] if next_m['title'] != 'Untitled Conversation' else m['title'],
                        "update_time": next_m['ts'] or m['ts'],
                        "payload": {
                            "kind": "interaction",
                            "user_query": m['text'],
                            "ai_response": next_m['text'],
                            "snippet": f"USER: {m['text']}\n\nAI: {next_m['text']}",
                            "app": m.get('app_source', 'ChatGPT')
                        }
                    })
                    i += 2
                    paired = True

        if not paired:
            all_items.append({
                "conversation_id": m['cid'],
                "current_node_id": m['id'],
                "title": m['title'],
                "update_time": m['ts'],
                "payload": {
                    "kind": "message",
                    "role": m['role'],
                    "snippet": m['text'],
                    "app": m.get('app_source', 'ChatGPT')
                }
            })
            i += 1

    # Add forensic highlights (Njullu, etc.)
    print("Checking final_cache_forensic_report.md...")
    try:
        if os.path.exists("final_cache_forensic_report.md"):
            with open("final_cache_forensic_report.md", "r", encoding="utf-8") as f:
                content = f.read()
            # Improved regex: Stop at the next header (### or ##)
            highlights = re.finditer(r'### Topic:[ \t]*(.*?)\r?\n(.*?)(?=\r?\n###|\r?\n##|\Z)', content, re.S)
            count = 0
            for h in highlights:
                topic = h.group(1).strip()
                body = h.group(2).strip()
                
                # Filter out pure metadata/system notes
                if "*Metadata indicates" in body or "found in raw cache block" in body.lower():
                    if topic != "Njullu": # Keep Njullu as requested by user previously, but clean it
                        pass
                
                print(f"Found highlight: {topic}")
                all_items.append({
                    "conversation_id": f"forensic_{hashlib.md5(topic.encode()).hexdigest()[:8]}",
                    "current_node_id": f"forensic_node_{hashlib.md5(body.encode()).hexdigest()[:8]}",
                    "title": f"Forensic Hit: {topic}",
                    "update_time": 1773155000,
                    "payload": {
                        "kind": "forensic_carve",
                        "topic": topic,
                        "snippet": body
                    }
                })
                count += 1
            print(f"Added {count} items from forensic report.")
    except Exception as e: 
        print(f"Error reading forensic report: {e}")

    # Add Truly Deleted Fragments
    print("Checking TRULY_DELETED_RECOVERY.md...")
    try:
        if os.path.exists("TRULY_DELETED_RECOVERY.md"):
            with open("TRULY_DELETED_RECOVERY.md", "r", encoding="utf-8") as f:
                content = f.read()
            # Robust regex for fragments
            fragments = re.finditer(r'### Fragment \d+ \(Source:[ \t]*(.*?)\)\s*\r?\n>[ \t]*(.*?)(?=\r?\n###|\Z)', content, re.S)
            count = 0
            for frag in fragments:
                source = frag.group(1).strip()
                text = frag.group(2).strip()
                all_items.append({
                    "conversation_id": "deleted_fragment_pool",
                    "current_node_id": f"deleted_{hashlib.md5(text.encode()).hexdigest()[:8]}",
                    "title": "Deleted Fragment Recovery",
                    "update_time": 1773154000,
                    "payload": {
                        "kind": "message",
                        "role": "unknown",
                        "snippet": text,
                        "forensic_source": source
                    }
                })
                count += 1
            print(f"Added {count} fragments from TRULY_DELETED_RECOVERY.md.")
    except Exception as e:
        print(f"Error reading deleted recovery: {e}")

    # Filter/Sort Search History
    final_items = []
    seen_snips = set()
    for it in all_items:
        snip = it['payload'].get('snippet', '')
        if not snip: continue
        # use a more lenient hash for dedup of forensic items
        h = hashlib.md5(normalize_text(snip)[:1000].encode()).hexdigest()
        if h not in seen_snips:
            seen_snips.add(h)
            it['update_time_decoded'] = datetime.fromtimestamp(it['update_time']).strftime('%Y-%m-%d %H:%M:%S') if it['update_time'] else "UNKNOWN"
            final_items.append(it)

    # Final Sort: Newest -> Oldest
    final_items.sort(key=lambda x: x['update_time'], reverse=True)
    
    # SPLIT BY APP
    apps = {
        "ChatGPT": [it for it in final_items if it['payload'].get('app') == 'ChatGPT'],
        "Claude": [it for it in final_items if it['payload'].get('app') == 'Claude']
    }

    for app_name, items in apps.items():
        if not items: continue
        
        prefix = app_name.upper()
        # Write JSON
        output_path = f"{prefix}_RECONSTRUCTED_HISTORY.json"
        print(f"Writing {len(items)} items to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, indent=2, ensure_ascii=False)

        # Write Markdown
        md_path = f"{prefix}_RECONSTRUCTED_HISTORY.md"
        print(f"Writing human-readable report to {md_path}...")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {app_name} Reconstructed History\n")
            f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
            f.write(f"*Total Unique Entries: {len(items)}*\n\n")
            
            for item in items:
                title = item.get("title", "Untitled Conversation")
                cid = item.get("conversation_id", "unknown")
                kind = item["payload"].get("kind", "message")
                snippet = item["payload"].get("snippet", "[No content]")
                ts = item.get("update_time_decoded", "UNKNOWN")
                
                f.write(f"## {title}\n")
                f.write(f"- **ID**: `{cid}`\n")
                f.write(f"- **Time**: {ts}\n")
                f.write(f"- **Source**: {kind}\n\n")
                
                clean_snippet = snippet.replace('\n', '\n> ')
                f.write(f"> {clean_snippet}\n\n")
                f.write("---\n\n")

    print("Success. Separate report files created.")

if __name__ == "__main__":
    produce_json_report()

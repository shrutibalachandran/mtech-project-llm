import json
import re
import hashlib
from datetime import datetime

def normalize_text(text):
    if not text: return ""
    return re.sub(r'\s+', '', text).lower()

def extract_timestamp_from_text(text):
    # Matches "2026-03-09T09:45:53.094035Z" or "-01-11T00:43:18.98"
    pattern = r'(?:202)?\d-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?'
    matches = re.findall(pattern, text)
    if not matches:
        return 0
    
    # Try parsing the first/latest one
    best_ts = 0
    for match in matches:
        dt_str = match.replace('Z', '')
        # Handle cases where year is truncated (e.g., "-01-11...")
        if dt_str.startswith('-'):
            # Assume 2026 for Jan/Feb/Mar, 2025 for others as a heuristic
            month = int(dt_str[1:3])
            year = "2026" if month <= 4 else "2025"
            dt_str = year + dt_str
        elif not dt_str.startswith('202'):
             # If it starts with a single digit like "6-03-10", it might be missing "202"
             dt_str = "202" + dt_str

        if '.' in dt_str:
            base, frac = dt_str.split('.')
            frac = frac[:6]
            dt_str = f"{base}.{frac}"
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S.%f")
            except: continue
        else:
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
            except: continue
        
        ts = dt.timestamp()
        if ts > best_ts:
            best_ts = ts
    return best_ts

def is_junk(text):
    """Filters out application telemetry, cookies, and binary debris while preserving chat JSON."""
    # SIGNAL: If these keys or specific user-requested topics are present, keep them.
    signal_keywords = [
        r'\"title\":', r'\"text_fragments\":', r'\"conversation_id\":',
        r'\"messages\":', r'\"author\":', r'\"content\":',
        r'njullu', r'alphabet', r'forensics', r'search_history'
    ]
    
    # NOISE: Patterns strongly associated with application telemetry and junk.
    junk_patterns = [
        r'statsig', r'cloudflare', r'challenge', r'oai/apps/', r'performance',
        r'debugSettings', r'telemetry', r'Cookie', r'Auth0', r'NextAuth',
        r'lastExternalReferrer', r'homepage_prompt_style', r'goog_log', r'sentry',
        r'\"jsonViewerFilters\"', r'perfStore', r'cluster_reg', r'app_window',
        r'\"first_input_to_', r'\"stream_update_', r'\"bytes_received\"',
        r'textdocs', r'cdn/assets'
    ]
    
    norm = text.lower()
    
    # 1. Check for Signal Overrides First
    if any(re.search(p, norm) for p in signal_keywords):
        return False
    
    # 2. Check for Junk Patterns
    if any(re.search(p, norm) for p in junk_patterns):
        return True
    
    # 3. Check for low information content
    alphanumeric = len(re.sub(r'[^a-zA-Z0-9]', '', text))
    ratio_threshold = 0.3 if text.strip().startswith('{') else 0.4
    
    if len(text) > 0 and (alphanumeric / len(text)) < ratio_threshold:
        # Final safety check for keywords
        if any(kw in norm for kw in ['njullu', 'alphabet', 'forensics']):
            return False
        return True
        
    return False


def main():
    try:
        with open('RECONSTRUCTED_HISTORY.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("RECONSTRUCTED_HISTORY.json not found.")
        return

    conversations = data.get('conversations', [])
    
    # Strip any previously added forensic fragments to allow clean regeneration
    original_conversations = [
        c for c in conversations 
        if c.get('conversation_id') != "deleted_and_unassigned_fragments" 
        and not str(c.get('conversation_id', '')).startswith('deleted_frag_')
        and not str(c.get('conversation_id', '')).startswith('search_frag_')
    ]

    
    known_snippets = set()
    for conv in original_conversations:
        times = [m.get('timestamp', 0) for m in conv.get('messages', []) if m.get('timestamp', 0) > 0]
        if times:
            conv['start_time'] = min(times)
            conv['end_time'] = max(times)
            
        for msg in conv.get('messages', []):
            text = msg.get('text', '')
            norm = normalize_text(text)
            if len(norm) > 10:
                known_snippets.add(norm[:100])
                
    try:
        with open('forensic_report.txt', 'r', encoding='utf-8') as f:
            forensic_content = f.read()
    except FileNotFoundError:
        forensic_content = ""

    deleted_convs = []
    parts = re.split(r'--- Extracted from .*? ---', forensic_content)
    
    for i, p in enumerate(parts[1:]):
        text = p.strip()
        if len(text) < 40: continue # Higher threshold for fragments
        if is_junk(text): continue
            
        norm = normalize_text(text)
        if norm[:100] not in known_snippets:
            if len(norm) > 10: known_snippets.add(norm[:100])
                
            ts = extract_timestamp_from_text(text)
            time_decoded = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts > 0 else "UNKNOWN"
            
            title_snip = text[:40].replace('\n', ' ').strip()
            if len(title_snip) < 3: title_snip = "Fragment"
            
            deleted_convs.append({
                "conversation_id": f"deleted_frag_{i}",
                "title": f"Deleted Fragment: {title_snip}...",
                "start_time": ts,
                "end_time": ts,
                "is_archived": False,
                "messages": [{
                    "id": f"msg_frag_{i}",
                    "role": "FRAGMENT",
                    "text": text,
                    "timestamp": ts,
                    "timestamp_decoded": time_decoded
                }]
            })
            
    # Load additional fragments from source recovery if they were missed
    try:
        with open('RECOVERED_HISTORY_CLEAN.json', 'r', encoding='utf-8') as f:
            source_data = json.load(f)
            source_items = source_data.get('items', [])
            for item in source_items:
                payload = item.get('payload', {})
                snippet = payload.get('snippet', '')
                if not is_junk(snippet):
                    norm = normalize_text(snippet)
                    if norm[:100] not in known_snippets:
                        known_snippets.add(norm[:100])
                        ts = item.get('update_time', 0)
                        time_decoded = item.get('update_time_decoded', 'UNKNOWN')
                        
                        # Use the original search node ID as the forensic ID
                        node_id = item.get('current_node_id')
                        if not node_id:
                            print(f"DEBUG: Missing current_node_id for fragment: {snippet[:20]}")
                            node_id = f"search_frag_{len(deleted_convs)}"

                        
                        deleted_convs.append({
                            "conversation_id": node_id,
                            "title": f"Recovered Search: {snippet[:40]}...",
                            "start_time": ts,
                            "end_time": ts,
                            "is_archived": False,
                            "messages": [{
                                "id": f"msg_{node_id}",
                                "role": "FRAGMENT",
                                "text": snippet,
                                "timestamp": ts,
                                "timestamp_decoded": time_decoded
                            }]
                        })


    except Exception as e:
        print(f"Note: Could not load source fragments: {e}")

    # Combine
    all_conversations = original_conversations + deleted_convs
    
    # STRICT SORT: Newest to Oldest (Latest timestamp wins, then newest start time)
    all_conversations.sort(key=lambda x: (max(x.get('end_time', 0), x.get('start_time', 0)), x.get('start_time', 0)), reverse=True)

    
    # Sort messages within each conversation from newest to oldest
    for conv in all_conversations:
        conv['messages'].sort(key=lambda x: x.get('timestamp') or 0, reverse=True)

    data['conversations'] = all_conversations
    
    with open('RECONSTRUCTED_HISTORY.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"Cleaned and added {len(deleted_convs)} valid chat fragments. Total conversations: {len(all_conversations)}")
    
    # Re-generate Markdown from the sorted JSON
    with open("RECONSTRUCTED_HISTORY.md", "w", encoding="utf-8") as f:
        f.write("# Forensic Reconstruction Report: ChatGPT History (LATEST TO EARLIEST)\n\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total Conversations: {len(all_conversations)}\n\n---\n\n")
        
        for conv in all_conversations:
            f.write(f"## {conv['title']}\n")
            f.write(f"- **ID**: `{conv['conversation_id']}`\n")
            time_str = "UNKNOWN to UNKNOWN"
            if conv['start_time'] or conv['end_time']:
                start_str = datetime.fromtimestamp(conv['start_time']).strftime('%Y-%m-%d %H:%M:%S') if conv['start_time'] else '...'
                end_str = datetime.fromtimestamp(conv['end_time']).strftime('%Y-%m-%d %H:%M:%S') if conv['end_time'] else '...'
                time_str = f"{start_str} to {end_str}"
                
            f.write(f"- **Period**: {time_str}\n")
            if conv['is_archived']: f.write("- **Status**: Archived\n")
            f.write("\n")
            
            for m in conv['messages']:
                tag = "**USER**" if m['role'] == 'user' else "**AI**" if m['role'] == 'assistant' else "**EXTRACTED FRAGMENT**"
                f.write(f"{tag} ({m['timestamp_decoded']}):\n")
                f.write(f"{m['text']}\n\n")
            f.write("---\n\n")

    print("Success: Final report sorted newest-first and filtered for chat messages.")

if __name__ == '__main__':
    main()

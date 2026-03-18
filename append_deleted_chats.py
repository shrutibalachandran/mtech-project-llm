import json
import re
import hashlib
from datetime import datetime

def normalize_text(text):
    if not text: return ""
    return re.sub(r'\s+', '', text).lower()

def main():
    # Load existing reconstructed history
    try:
        with open('RECONSTRUCTED_HISTORY.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("RECONSTRUCTED_HISTORY.json not found.")
        return

    conversations = data.get('conversations', [])
    
    # Sort conversations from latest to earliest based on end_time or start_time
    conversations.sort(key=lambda x: x.get('end_time') or x.get('start_time') or 0, reverse=True)
    
    # Sort messages within each conversation from latest to earliest
    for conv in conversations:
        conv['messages'].sort(key=lambda x: x.get('timestamp') or 0, reverse=True)

    # Collect known message hashes/snippets to avoid duplicates
    known_snippets = set()
    for conv in conversations:
        for msg in conv['messages']:
            text = msg.get('text', '')
            norm = normalize_text(text)
            if len(norm) > 10:
                known_snippets.add(norm[:100]) # Use first 100 chars of normalized text for matching
                
    # Read forensic_report.txt for deleted/unassigned fragments
    try:
        with open('forensic_report.txt', 'r', encoding='utf-8') as f:
            forensic_content = f.read()
    except FileNotFoundError:
        print("forensic_report.txt not found. Skipping deleted chats extraction.")
        forensic_content = ""

    deleted_messages = []
    
    # Split by the extraction headers
    parts = re.split(r'--- Extracted from .*? ---', forensic_content)
    for p in parts[1:]:
        text = p.strip()
        if len(text) < 20:
            continue
            
        norm = normalize_text(text)
        # Check if this fragment looks like it's already in the known history
        if norm[:100] not in known_snippets:
            # We also want to skip pure metadata like JSON headers if it's junk, but let's include all unique text
            if len(norm) > 10:
                known_snippets.add(norm[:100])
                
            # Filter out some pure JSON structure junk if it isn't a message
            if text.startswith('{"value":{"pages":[') or text.startswith('{"state":{"debugMode"'):
                continue
                
            deleted_messages.append({
                "id": f"deleted_frag_{len(deleted_messages)+1}",
                "role": "unknown",
                "text": text,
                "timestamp": 0,
                "timestamp_decoded": "UNKNOWN (Deleted/Fragment)"
            })
            
    if deleted_messages:
        # Add as a special conversation
        deleted_conv = {
            "conversation_id": "deleted_and_unassigned_fragments",
            "title": "Deleted & Unassigned Chat Fragments",
            "start_time": 0,
            "end_time": 0,
            "is_archived": False,
            "messages": deleted_messages
        }
        # Append to the end of conversations list
        conversations.append(deleted_conv)

    data['conversations'] = conversations
    
    # Save back JSON
    with open('RECONSTRUCTED_HISTORY.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"Added {len(deleted_messages)} deleted/unassigned fragments to RECONSTRUCTED_HISTORY.json")
    
    # Re-generate Markdown
    with open("RECONSTRUCTED_HISTORY.md", "w", encoding="utf-8") as f:
        f.write("# Forensic Reconstruction Report: ChatGPT History\n\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total Conversations: {len(conversations)}\n\n---\n\n")
        
        for conv in conversations:
            f.write(f"## {conv['title']}\n")
            f.write(f"- **ID**: `{conv['conversation_id']}`\n")
            time_str = "UNKNOWN to UNKNOWN"
            if conv['start_time'] or conv['end_time']:
                start_str = datetime.fromtimestamp(conv['start_time']).strftime('%Y-%m-%d %H:%M:%S') if conv['start_time'] else '...'
                end_str = datetime.fromtimestamp(conv['end_time']).strftime('%Y-%m-%d %H:%M:%S') if conv['end_time'] else '...'
                time_str = f"{start_str} to {end_str}"
            elif conv['conversation_id'] == "deleted_and_unassigned_fragments":
                time_str = "Various / Unknown Dates"
                
            f.write(f"- **Period**: {time_str}\n")
            if conv['is_archived']: f.write("- **Status**: Archived\n")
            f.write("\n")
            
            for m in conv['messages']:
                role_label = "**USER**" if m['role'] == 'user' else "**AI**" if m['role'] == 'assistant' else f"**{m['role'].upper()}**"
                f.write(f"{role_label} ({m['timestamp_decoded']}):\n")
                f.write(f"{m['text']}\n\n")
            f.write("---\n\n")

    print("Successfully updated RECONSTRUCTED_HISTORY.md with sorted chats and deleted fragments.")

if __name__ == '__main__':
    main()

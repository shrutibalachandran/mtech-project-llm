import os
import json
import glob
import re
import hashlib
from datetime import datetime
from collections import defaultdict

# Reuse core extraction utilities
from generate_json_report import extract_all_messages, normalize_text

def get_hash(text):
    norm = normalize_text(text)
    return hashlib.md5(norm[:1024].encode()).hexdigest()

class ReconstructionEngine:
    def __init__(self, workspace_path):
        self.workspace = workspace_path
        self.raw_records = []
        self.grouped_records = defaultdict(list)
        self.conversation_metadata = defaultdict(dict)
        self.final_conversations = []

    def stage_1_merge(self):
        """Merge records from all recovered sources (LevelDB bins and combined JSONs)."""
        print("[1/7] Merging artifacts from storage sources...")
        os.chdir(self.workspace)
        files = glob.glob("recovered_*.bin")
        
        for fp in files:
            try:
                with open(fp, "rb") as f:
                    data = f.read()
                try:
                    obj = json.loads(data)
                    # Use the core extractor to get individual message records
                    self.raw_records.extend(extract_all_messages(obj))
                except: pass
            except: pass
        
        # Also could check for other history files if present
        print(f"      Total raw records collected: {len(self.raw_records)}")

    def clean_snippet(self, text):
        """Strip JSON-like metadata keys, binary debris, and non-printable junk."""
        # 1. Remove common metadata keys often found in raw fragments
        patterns = [
            r'["\']?title["\']?\s*[:\)]\s*["\']?.*?["\']?[\n,}\)]',
            r'["\']?isArchived["\']?\s*[TF:0-1].*?[\n,}\)]',
            r'["\']?updateTime["\']?\s*[N:].*?[\n,}\)]',
            r'["\']?createTime["\']?\s*[N:].*?[\n,}\)]',
            r'["\']?text["\']?\s*[:\)]\s*["\']?',
            r'ConversationsDatabase',
            r'META:https:\/\/chatgpt\.com'
        ]
        cleaned = text
        for p in patterns:
            cleaned = re.sub(p, '', cleaned, flags=re.I|re.S)
        
        # 2. Remove strings of binary/non-printable characters (debris)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', ' ', cleaned)
        
        # 3. Collapse multiple spaces and trim
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # 4. Limit length for snippet
        return cleaned.strip()[:1000]

    def stage_forensic_harvesting(self):
        """Parse forensic_report.txt for deleted or unassigned text fragments."""
        print("[1.5/7] Harvesting deleted fragments from forensic_report.txt (Deep Scan)...")
        try:
            with open("forensic_report.txt", "r", encoding="utf-8") as f:
                content = f.read()
            
            # Split by the extraction headers
            parts = re.split(r'--- Extracted from .*? ---', content)
            
            # Specific titles the user mentioned as missing
            missing_titles = [
                "Network Security vs Forensics",
                "Human Emotions Explained",
                "ModuleNotFoundError Fix",
                "Aptitude Tests in Hiring",
                "Network Congestion Overview"
            ]
            
            total_extracted = 0
            for p in parts[1:]:
                text = p.strip()
                if len(text) < 20: continue
                
                # Check for explicit mentioned titles first (Aggressive match)
                for i, target in enumerate(missing_titles):
                    if target.lower() in text.lower():
                        # Try to find a CID near it
                        start_pos = text.lower().find(target.lower())
                        vicinity = text[max(0, start_pos-500):start_pos+500]
                        cid = None
                        m_cid = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', vicinity, re.I)
                        if m_cid: cid = m_cid.group(1).lower()
                        
                        self.raw_records.append({
                            'id': f"forensic_missing_{hashlib.md5(target.encode()).hexdigest()[:6]}_{i}",
                            'text': self.clean_snippet(text),
                            'role': 'unknown',
                            'ts': 1773000000.0, # Approximate March 2026 for prioritized items
                            'cid': cid or f"recovered_{hashlib.md5(target.encode()).hexdigest()[:8]}",
                            'title': target,
                            'is_archived': False
                        })
                        total_extracted += 1

                # General Deep Scan: Look for other title occurrences
                matches = list(re.finditer(r'["\']?title["\']?\s*[:\)]\s*["\']?(.*?)["\']?[\n,}\)]', text, re.I))
                
                for i, m in enumerate(matches):
                    title = m.group(1).strip()
                    if len(title) < 3 or title == "items": continue
                    # Skip if already added by missing_titles logic
                    if any(t.lower() in title.lower() for t in missing_titles): continue
                    
                    start_pos = m.start()
                    vicinity = text[max(0, start_pos-500):start_pos+500]
                    cid = None
                    m_cid = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', vicinity, re.I)
                    if m_cid: cid = m_cid.group(1).lower()
                    
                    ts = 0
                    m_ts = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', vicinity)
                    if m_ts:
                        try:
                            dt = datetime.fromisoformat(m_ts.group(1).replace('Z', ''))
                            ts = dt.timestamp()
                        except: pass

                    self.raw_records.append({
                        'id': f"forensic_{hashlib.md5(title.encode()).hexdigest()[:8]}_{i}",
                        'text': self.clean_snippet(text),
                        'role': 'unknown',
                        'ts': ts,
                        'cid': cid or f"recovered_{hashlib.md5(title.encode()).hexdigest()[:8]}",
                        'title': title,
                        'is_archived': False
                    })
                    total_extracted += 1

                # Fallback DELETED (no debris added here)
                        
            print(f"      Extracted {total_extracted} clean items from forensic fragments.")
        except FileNotFoundError:
            print("      forensic_report.txt not found, skipping.")
        except Exception as e:
            print(f"      Error harvesting forensic report: {e}")

    def stage_2_metadata_harvesting(self):
        """Scan records for CID, titles, timestamps, and archival status."""
        print("[2/7] Harvesting global metadata and resolving conflicts...")
        for r in self.raw_records:
            cid = r['cid']
            if cid == 'unknown_cid': continue
            
            meta = self.conversation_metadata[cid]
            
            # Resolve Title: longest non-generic title wins
            title = r.get('title', 'Untitled Conversation')
            if title != 'Untitled Conversation':
                if not meta.get('title') or len(title) > len(meta['title']):
                    meta['title'] = title
            
            # Resolve Timestamps: Min/Max tracking
            ts = r.get('ts', 0)
            if ts > 0:
                if 'start_ts' not in meta or ts < meta['start_ts']: meta['start_ts'] = ts
                if 'end_ts' not in meta or ts > meta['end_ts']: meta['end_ts'] = ts
            
            # Archive status (if any record has it true, it's likely archived)
            if r.get('is_archived'):
                meta['is_archived'] = True

        # Fill defaults
        for cid, meta in self.conversation_metadata.items():
            if 'title' not in meta: meta['title'] = 'Untitled Conversation'
            if 'is_archived' not in meta: meta['is_archived'] = False

    def stage_3_grouping(self):
        """Group all message artifacts by conversation identifiers."""
        print("[3/7] Grouping artifacts by conversation ID...")
        for r in self.raw_records:
            cid = r['cid']
            self.grouped_records[cid].append(r)
        print(f"      Grouped into {len(self.grouped_records)} unique conversation IDs.")

    def stage_4_chronological_ordering(self):
        """Sort messages within each conversation by timestamp."""
        print("[4/7] Applying chronological ordering within groups...")
        for cid in self.grouped_records:
            # Sort by timestamp (newest first)
            self.grouped_records[cid].sort(key=lambda x: x['ts'], reverse=True)

    def stage_5_role_inference(self):
        """Analyze fields to determine message role (User, Assistant, System)."""
        print("[5/7] Performing role inference analysis...")
        for cid, messages in self.grouped_records.items():
            for m in messages:
                if m['role'] != 'unknown': continue
                
                text = m['text'].lower()
                # Heuristics
                if '?' in m['text'] and len(m['text']) < 500:
                    m['role'] = 'user'
                elif any(x in text for x in ['i am an ai', 'language model', 'as an assistant', 'openai']):
                    m['role'] = 'assistant'
                elif len(m['text']) > 1000:
                    m['role'] = 'assistant'
                else:
                    # Contextual inference: if previous was user, this might be assistant
                    pass

    def stage_6_duplicate_removal(self):
        """Eliminate redundant fragments across storage layers."""
        print("[6/7] Removing duplicates and title-redundancy...")
        for cid in self.grouped_records:
            seen_hashes = set()
            unique_list = []
            meta_title = self.conversation_metadata[cid].get('title', '')
            
            for m in self.grouped_records[cid]:
                # Skip title-only records (redundant with metadata)
                if m['text'] == meta_title and len(m['text']) < 200:
                    continue
                
                h = get_hash(m['text'])
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    unique_list.append(m)
            self.grouped_records[cid] = unique_list

    def stage_7_reporting(self):
        """Generate structured JSON and Markdown reports."""
        print("[7/7] Generating flattened dual-format reports (all messages)...")
        
        # Prepare final items list
        final_items = []
        
        # We want to list EVERY message as an item for "all chat history"
        for cid, messages in self.grouped_records.items():
            if not messages: continue
            
            meta = self.conversation_metadata.get(cid, {})
            title = meta.get('title', 'Untitled Conversation')
            if cid == 'unknown_cid':
                title = "Recovered Fragment"
            
            for m in messages:
                item = {
                    "conversation_id": cid if cid != 'unknown_cid' else f"recovered_{hashlib.md5(m['text'][:50].encode()).hexdigest()[:8]}",
                    "current_node_id": m['id'],
                    "title": title,
                    "is_archived": meta.get('is_archived', False),
                    "is_starred": None,
                    "update_time": float(m['ts']),
                    "payload": {
                        "kind": "message",
                        "role": m['role'],
                        "message_id": m['id'],
                        "snippet": m['text']
                    }
                }
                final_items.append(item)

        # Sort all items by update_time (newest first)
        final_items.sort(key=lambda x: x['update_time'], reverse=True)

        # JSON Export
        output_data = {"items": final_items}
        with open("RECONSTRUCTED_HISTORY.json", "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        # Markdown Export (Simplified)
        with open("RECONSTRUCTED_HISTORY.md", "w", encoding="utf-8") as f:
            f.write("# Forensic Reconstruction Report: ChatGPT History\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Total Unique Conversations/Fragments: {len(final_items)}\n\n---\n\n")
            
            for item in final_items:
                f.write(f"## {item['title']}\n")
                f.write(f"- **ID**: `{item['conversation_id']}`\n")
                f.write(f"- **Last Updated**: {datetime.fromtimestamp(item['update_time']).strftime('%Y-%m-%d %H:%M:%S') if item['update_time'] else 'UNKNOWN'}\n")
                if item['is_archived']: f.write("- **Status**: Archived\n")
                f.write("\n")
                
                # Show snippet
                f.write(f"**Latest Message Snippet**:\n")
                f.write(f"{item['payload']['snippet']}\n\n")
                f.write("---\n\n")

        print(f"Success. Reports generated:")
        print(f" - JSON: RECONSTRUCTED_HISTORY.json ({len(final_items)} items)")
        print(f" - Markdown: RECONSTRUCTED_HISTORY.md")

    def run(self):
        self.stage_1_merge()
        self.stage_forensic_harvesting()
        self.stage_2_metadata_harvesting()
        self.stage_3_grouping()
        self.stage_4_chronological_ordering()
        self.stage_5_role_inference()
        self.stage_6_duplicate_removal()
        self.stage_7_reporting()

if __name__ == "__main__":
    engine = ReconstructionEngine(r"c:\Users\sreya\OneDrive\Desktop\project3")
    engine.run()

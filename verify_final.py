"""
verify_final.py - Spot-check that key conversation titles are present in the final output
"""
import json

with open('reports/RECOVERED_CHATGPT_HISTORY.json', encoding='utf-8') as f:
    rec = json.load(f)
items = rec['items']

# Titles from user's screenshot (greyed out means 'Grammar Correction Explanation' is deleted)
check_titles = [
    "Forensic Test Overview",
    "Network Security vs Forensics",
    "Human Emotions Explained",
    "ModuleNotFoundError Fix",
    "Aptitude Tests in Hiring",
    "Network Congestion Overview",
    "Forensic evidence in ChatGPT",
    "PEAS description part picking",
    "Soft Computing Exam Guide",
    "Bibliography extraction",
    "Grammar Correction Explanation",   # greyed = deleted
]

title_map = {}
for i in items:
    t = i.get('title','')
    if t not in title_map:
        title_map[t] = i

print(f"=== Final output: {len(items)} total conversations ===\n")
print("Key title check:")
for t in check_titles:
    if t in title_map:
        e = title_map[t]
        deleted = e.get('is_deleted', False)
        snip = e.get('payload',{}).get('snippet','')[:60]
        print(f"  [OK{'  DELETED' if deleted else ''}] {t}")
        print(f"         cid={e.get('conversation_id','')[:20]}... snip={repr(snip)}")
    else:
        print(f"  [MISS] {t}")

print()
total = len(items)
deleted_count = sum(1 for i in items if i.get('is_deleted'))
with_content = sum(1 for i in items if not (
    i.get('payload',{}).get('snippet','').startswith('[No cached') or
    i.get('payload',{}).get('snippet','').startswith('[Deleted')
))
print(f"Summary:")
print(f"  Total: {total}")
print(f"  With real content: {with_content}")
print(f"  Deleted/orphaned: {deleted_count}")
print(f"  Title-only placeholders: {total - with_content - deleted_count}")

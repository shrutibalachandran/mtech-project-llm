"""
check_orphans.py - Check HARVESTED_CIDS and ORPHANED_CID_DETAILS for missing conversations
"""
import json

# Load current recovered output
with open('reports/RECOVERED_CHATGPT_HISTORY.json', encoding='utf-8') as f:
    rec = json.load(f)
existing_cids = {i['conversation_id'] for i in rec['items'] if i.get('conversation_id')}
existing_titles = {i['title'] for i in rec['items']}
print("Existing CIDs:", len(existing_cids))

# HARVESTED: list of UUID strings
with open('HARVESTED_CIDS.json', encoding='utf-8') as f:
    h = json.load(f)
harvested_set = set(s.strip().lower() for s in h if isinstance(s, str))
missing_from_harvested = harvested_set - existing_cids
print("Harvested CIDs total:", len(harvested_set))
print("Harvested CIDs NOT in recovered output:", len(missing_from_harvested))

# ORPHANED: each has {cid, titles[], sources[], snippets[]}
with open('ORPHANED_CID_DETAILS.json', encoding='utf-8') as f:
    o = json.load(f)

useful_orphans = []
for e in o:
    cid = e.get('cid', '').lower()
    titles = e.get('titles', [])
    snippets = e.get('snippets', [])
    # Pick best title
    good_titles = [t for t in titles if t and t.strip() and t.strip() not in ('New chat', '')]
    if not good_titles:
        continue
    title = good_titles[0]
    snip = snippets[0] if snippets else ''
    if cid not in existing_cids:
        useful_orphans.append({'cid': cid, 'title': title, 'snippet': snip})

print("Orphaned entries (not in recovered, with titles):", len(useful_orphans))
print()
print("Sample orphaned entries:")
for e in useful_orphans[:10]:
    print(" ", e['cid'], "|", repr(e['title']), "|", repr(e['snippet'][:60]))

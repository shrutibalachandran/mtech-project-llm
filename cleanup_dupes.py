import json

path = r'reports/RECOVERED_CLAUDE_HISTORY.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

# Remove the two truncated blob_26 duplicates with partial titles
bad_titles = {'ting data from LLMs!', 's generative AI'}
before = len(d['items'])
d['items'] = [x for x in d['items'] if x.get('title') not in bad_titles]
removed = before - len(d['items'])

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print(f"Removed {removed} partial duplicate entries. Total items: {len(d['items'])}")

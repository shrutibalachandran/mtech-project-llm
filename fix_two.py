import json

path = r'reports/RECOVERED_CLAUDE_HISTORY.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

for item in d['items']:
    title = item.get('title', '')
    if title == 'Deadliest disease in the world' or title == 'Bat and ball definitions':
        # Apply the fix to make them match the active blob payload style
        if item['payload'].get('snippet', '').startswith('[No cached content]'):
            item['payload']['snippet'] = '[Recovered from IndexedDB blob - V8 serialized conversation list]'
            item['source_file'] = 'IndexedDB/blob_26'

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print("Applied surgical fix to Deadliest disease and Bat and ball definitions.")

import json

path = r'reports/RECOVERED_CLAUDE_HISTORY.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

# Restore the original correct data for these two from claude_COMPLETE.json
originals = {
    "b880dca5-c2a6-417b-bb2c-9e55fb55cc9d": {
        "snippet": "[No cached content] created=2026-03-09T09:40:54.667394Z updated=2026-03-09T09:41:25.545773Z",
        "source_file": "data_1"
    },
    "29af3a99-64e0-4e9d-9bc2-4004eb2d19fa": {
        "snippet": "[No cached content] created=2026-02-11T11:03:40.601453Z updated=2026-02-11T11:03:51.554122Z",
        "source_file": "data_1"
    }
}

for item in d['items']:
    cid = item.get('conversation_id')
    if cid in originals:
        item['payload']['snippet'] = originals[cid]['snippet']
        item['source_file'] = originals[cid]['source_file']
        item['payload'].pop('role', None)  # remove any stray role field
        print(f"Restored: {item['title']}")

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print("Done.")

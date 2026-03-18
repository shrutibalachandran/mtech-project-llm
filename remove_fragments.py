import json

path = 'reports/RECOVERED_CLAUDE_HISTORY.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

old_len = len(d['items'])
# Remove deleted_fragment_pool items as the user requested
d['items'] = [x for x in d['items'] if x.get('conversation_id') != 'deleted_fragment_pool']

# Also remove claude_account_metadata
d['items'] = [x for x in d['items'] if x.get('conversation_id') != 'claude_account_metadata']

new_len = len(d['items'])

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    
print(f"Removed {old_len - new_len} noise items.")

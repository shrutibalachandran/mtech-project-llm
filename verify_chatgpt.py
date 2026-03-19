import json
from collections import Counter

with open('reports/RECOVERED_CHATGPT_HISTORY.json', encoding='utf-8') as f:
    data = json.load(f)
items = data['items']
total = len(items)
with_content = sum(1 for i in items if not i['payload']['snippet'].startswith('[No cached content]'))
no_content = total - with_content

title_counts = Counter(i['title'] for i in items)
dupe_titles = {t: c for t, c in title_counts.items() if c > 1}

print(f'Total conversations : {total}')
print(f'With real content   : {with_content}')
print(f'Placeholder only    : {no_content}')
print(f'Titles appearing >1x: {len(dupe_titles)}')
print()
print('Sample 5 newest entries:')
for item in items[:5]:
    ts = item['update_time']
    snip = item['payload']['snippet'][:80].replace('\n',' ')
    print(f'  [{ts}] {repr(item["title"])} => {snip}...')

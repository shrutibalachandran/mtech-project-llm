"""check_output.py – Verify quality of new pipeline output vs image order."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('reports/chatgpt/chatgpt_history.json', encoding='utf-8') as f:
    data = json.load(f)

print(f'=== NEW PIPELINE OUTPUT ===')
print(f'Total conversations: {data["total_conversations"]}')
print()
for item in data['items']:
    title  = item.get('title', '(untitled)')
    ts     = item.get('update_time_ist', '')[:19]
    snip   = item['payload']['snippet']
    has_content = not snip.startswith('[No')
    has_noise   = '{"conversation_id"' in snip or '}},{"' in snip
    flag = ''
    if has_content and has_noise:
        flag = '  *** NOISE IN SNIPPET'
    elif has_content:
        flag = '  [CONTENT OK]'
    else:
        flag = '  [no cache]'
    print(f'{ts} | {title}{flag}')
    if has_content:
        print(f'   snippet: {snip[:120]}')

import json,sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
d=json.load(open('reports/RECOVERED_CLAUDE_HISTORY.json',encoding='utf-8'))
items=d.get('items',[])
real=sum(1 for x in items if not x['payload']['snippet'].startswith('[No'))
meta=len(items)-real
print(f'Total: {len(items)}, Real content: {real}, Meta-only (No cache): {meta}')
print()
print('Sample meta-only entry:')
for x in items:
    if x['payload']['snippet'].startswith('[No'):
        print(json.dumps(x,indent=2,ensure_ascii=False)[:400])
        break

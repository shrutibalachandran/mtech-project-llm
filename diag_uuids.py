import re
data = open(r'temp_live_idb\blob_26.bin','rb').read()

bat_idx = data.find(b'Bat and ball defini')
print(f'Bat at offset: {bat_idx}')

lookback = data[max(0, bat_idx-600):bat_idx]
uuids = re.findall(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', lookback)
print('UUIDs in lookback:')
for u in uuids:
    print(' ', u.decode())

cyb_idx = data.find(b'Cyber for', 160000)
print(f'Cyber idx: {cyb_idx}')
if cyb_idx != -1:
    ctx = data[cyb_idx:cyb_idx+80]
    safe = ''.join(chr(b) if 32<=b<127 else f'[{b:02x}]' for b in ctx)
    print('Cyber ctx:', safe)
    cyb_lb = data[max(0,cyb_idx-400):cyb_idx]
    cu = re.findall(rb'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', cyb_lb)
    print('Cyber closest UUID:', cu[-1].decode() if cu else 'None')

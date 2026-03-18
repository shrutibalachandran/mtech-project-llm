"""
find_messages.py - Search blob_26.bin for actual message text near the 4 conversation UUIDs.
The blob is V8-serialized IndexedDB content - look for readable strings near each UUID.
"""
import re

BLOB = r'temp_live_idb\blob_26.bin'
data = open(BLOB, 'rb').read()

CONVS = {
    'Extracting data from LLMs':    b'0a5b59b4-fa0e-4e1b-9b42-27ab972b2c8c',
    'What is generative AI':         b'4619c6f8-5931-4745-a171-5550bb00bb54',
    'Deadliest disease in the world':b'b880dca5-c2a6-417b-bb2c-9e55fb55cc9d',
    'Bat and ball definitions':      b'29af3a99-64e0-4e9d-5530-4004eb2d19fa',
}

def extract_printable(data_bytes, start, length=2000):
    """Extract readable ASCII runs from a byte region."""
    region = data_bytes[start:start+length]
    runs = []
    current = []
    for b in region:
        if 32 <= b < 127 or b in (9, 10, 13):
            current.append(chr(b))
        else:
            if len(current) >= 5:
                runs.append(''.join(current))
            current = []
    if len(current) >= 5:
        runs.append(''.join(current))
    return runs

for title, uuid_bytes in CONVS.items():
    print(f"\n{'='*60}")
    print(f"CONVERSATION: {title}")
    idx = data.find(uuid_bytes)
    if idx == -1:
        # Try partial UUID
        partial = uuid_bytes[:20]
        idx = data.find(partial)
    if idx == -1:
        print("  UUID not found in blob")
        continue
    print(f"  UUID found at offset {idx}")
    
    # Extract readable strings in a 3000-byte window around this UUID
    runs = extract_printable(data, max(0, idx-500), 3000)
    print("  Readable strings:")
    for r in runs:
        r_clean = r.strip()
        if len(r_clean) > 8 and not r_clean.startswith('http') and not r_clean.startswith('//'):
            print(f"    {repr(r_clean[:300])}")

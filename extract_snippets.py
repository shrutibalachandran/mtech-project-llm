"""
extract_snippets.py
For each conversation, extract:
 - message UUID (leaf_message_id)
 - sender role (human/assistant)
 - text snippet
 - updated_at timestamp
from blob_26.bin V8 structure.
"""
import re

BLOB = r'temp_live_idb\blob_26.bin'
data = open(BLOB, 'rb').read()

# We know the conversation list is at ~160000-164000
# Each entry has: UUID -> name -> title -> created_at / updated_at -> leaf_message_id -> sender -> text
# Let's read a large window starting just before the entries and dump all readable content

# Find the start of the conversation list section
section_start = data.find(b'0a5b59b4-fa0e-4e1b-9b42-27ab972b2c8c')  # Extracting UUID
if section_start == -1:
    section_start = 160000

# Also find what comes AFTER the list - the 'Hi i am thinking' text is a snippet stored there
# Extract a window from section_start - 200 to +5000 and print full readable strings

window = data[section_start - 200: section_start + 5000]
print(f"Window size: {len(window)} bytes")

# Extract all printable runs >= 4 chars
runs = []
current = []
for b in window:
    if 32 <= b < 127:
        current.append(chr(b))
    else:
        s = ''.join(current).strip()
        if len(s) >= 4:
            runs.append(s)
        current = []
if current:
    s = ''.join(current).strip()
    if len(s) >= 4:
        runs.append(s)

print("\nAll printable strings in conversation section:")
for i, r in enumerate(runs):
    print(f"  [{i:3d}] {repr(r)}")

# Now find the "Hi i am thinking about LLM how to ex" run and look nearby for more
hi_idx = next((i for i,r in enumerate(runs) if 'Hi i am thinking' in r), None)
if hi_idx is not None:
    print(f"\n=== Context around message snippet (runs {hi_idx-5} to {hi_idx+10}) ===")
    for r in runs[max(0,hi_idx-5):hi_idx+15]:
        print(f"  {repr(r)}")

# Search for other snippets - "what is the deadliest", "bat and ball", "generative"
for keyword in ['deadliest', 'bat and', 'generative', 'what is', 'extract']:
    idxs = [i for i,r in enumerate(runs) if keyword.lower() in r.lower()]
    for i in idxs:
        print(f"\n=== Keyword '{keyword}' in run {i}: {repr(runs[i])} ===")
        nearby = runs[max(0,i-3):i+5]
        for r in nearby:
            print(f"  {repr(r)}")

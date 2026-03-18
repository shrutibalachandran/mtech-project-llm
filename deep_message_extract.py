"""
deep_message_extract.py
Find all printable text runs in blob_26.bin, especially message content.
Look for the leaf_message pointers and actual human/assistant turns.
"""
import re

BLOB = r'temp_live_idb\blob_26.bin'
data = open(BLOB, 'rb').read()

# We saw 'leaf_message' and '019cece5-b975-747a-a6a3-4c7892974f86' (for Extracting conv)
# and 'Hi i am thinking about LLM how to ex' at the end of the region
# Let's find where that text fragment is and read a bigger window

FRAGMENTS = [
    b'Hi i am thinking abo',
    b'what is the deadliest',
    b'What is the deadliest',
    b'what is generative',
    b'What is generative',
    b'bat and ball',
    b'Bat and ball',
    b'tuberculosis',
    b'generative AI is',
    b'cricket',
]

print("=== Searching entire blob for message content ===\n")
for needle in FRAGMENTS:
    idx = 0
    while True:
        idx = data.find(needle, idx)
        if idx == -1:
            break
        # Extract 400 bytes of readable text from here
        window = data[max(0,idx-50):idx+600]
        safe = ''.join(chr(b) if 32<=b<127 or b in(9,10,13) else ' ' for b in window)
        # Collapse whitespace for readability
        safe = ' '.join(safe.split())
        print(f"[FOUND] '{needle.decode()}' @ offset {idx}:")
        print(f"  {safe[:500]}")
        print()
        idx += 1

# Also dump a bigger window around the known 'Hi i am thinking' text
hi_idx = data.find(b'Hi i am thinking about LLM')
if hi_idx == -1:
    hi_idx = data.find(b'Hi i am thinking abo')
if hi_idx != -1:
    print(f"\n=== Extended window around 'Hi i am thinking' @ {hi_idx} ===")
    window = data[max(0,hi_idx-200):hi_idx+2000]
    # Print as printable runs
    current = []
    runs = []
    for b in window:
        if 32<=b<127 or b in(9,10,13):
            current.append(chr(b))
        else:
            if len(current)>=4:
                runs.append(''.join(current).strip())
            current=[]
    if len(current)>=4:
        runs.append(''.join(current).strip())
    for r in runs:
        if len(r) >= 5:
            print(f"  {repr(r)}")

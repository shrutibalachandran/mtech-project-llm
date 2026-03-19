"""Quick test for run.py pipelines (non-interactive)."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

import run

print('=== Testing ChatGPT pipeline ===')
paths_cg = run.discover_chatgpt_paths()
print('Paths:', {k: os.path.isdir(v) for k, v in paths_cg.items()})
run.run_chatgpt(paths_cg)

print()
print('=== Testing Claude pipeline ===')
paths_cl = run.discover_claude_paths()
print('Paths:', {k: os.path.isdir(v) for k, v in paths_cl.items()} if paths_cl else 'none found')
run.run_claude(paths_cl)

print()
print('=== Output files in reports/ ===')
import glob
for f in sorted(glob.glob('reports/*FORENSIC*')):
    size = os.path.getsize(f)
    print(f'  {f}  ({size:,} bytes)')

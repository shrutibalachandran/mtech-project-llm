"""test_pipelines.py – Quick verification of ChatGPT and Claude pipelines."""
import sys, io, os
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

# ─── ChatGPT ──────────────────────────────────────────────────────────────────
print("=" * 60)
print("TEST: ChatGPT Pipeline")
print("=" * 60)

import chatgpt_extractor, output_writer

paths = chatgpt_extractor.discover_paths()
print("Paths discovered:")
for k, v in paths.items():
    status = "OK  " if os.path.isdir(v) else "MISS"
    print(f"  [{status}] {k}")

convs = chatgpt_extractor.run(verbose=True)
print(f"\nConversations found: {len(convs)}")
print("Top 10:")
for c in convs[:10]:
    ts = float(c.get('update_time') or 0)
    dt = datetime.fromtimestamp(ts + 5.5*3600, tz=timezone.utc).strftime('%Y-%m-%d') if ts > 0 else 'N/A'
    msgs = len(c.get('messages', []))
    title = c.get('title', '')
    print(f"  {dt} | msgs={msgs} | {title}")

print("\nWriting output...")
result = output_writer.write_outputs("chatgpt", convs)
print(f"Written: {result}")

# ─── Claude ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST: Claude Pipeline")
print("=" * 60)

import claude_extractor

paths_c = claude_extractor.discover_paths()
print("Paths discovered:")
for k, v in paths_c.items():
    status = "OK  " if os.path.isdir(v) else "MISS"
    print(f"  [{status}] {k}")

convs_c = claude_extractor.run(verbose=True)
print(f"\nConversations found: {len(convs_c)}")
for c in convs_c[:5]:
    ts = float(c.get('update_time') or 0)
    dt = datetime.fromtimestamp(ts + 5.5*3600, tz=timezone.utc).strftime('%Y-%m-%d') if ts > 0 else 'N/A'
    print(f"  {dt} | {c.get('title','')}")

print("\nWriting output...")
result_c = output_writer.write_outputs("claude", convs_c)
print(f"Written: {result_c}")

print("\n=== ALL DONE ===")

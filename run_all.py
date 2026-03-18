"""
run_all.py
==========
One-command forensic pipeline for Claude chat recovery.

Steps:
  1. Save all manually-curated items from the current RECOVERED_CLAUDE_HISTORY.json
  2. Run forensic_main.py to freshly extract from live Claude AppData
  3. Run extract_blob_convs.py to append IndexedDB blob entries
  4. Merge: add back any curated items not already present (by conversation_id)
  5. Strip noise (deleted_fragment_pool, claude_account_metadata)
  6. Sort newest-first and save

Usage:
    python run_all.py
"""

import json
import os
import subprocess
import sys

OUT = "reports/RECOVERED_CLAUDE_HISTORY.json"

# ── 1. Save curated items ─────────────────────────────────────────────────────
curated = []
if os.path.exists(OUT):
    try:
        with open(OUT, "r", encoding="utf-8") as f:
            existing = json.load(f)
        curated = existing.get("items", [])
        print(f"[1] Saved {len(curated)} curated items from existing file.")
    except Exception as e:
        print(f"[1] Could not read existing file ({e}), starting fresh.")

# ── 2. Run forensic_main.py ───────────────────────────────────────────────────
print("\n[2] Running forensic_main.py (live extraction)...")
result = subprocess.run([sys.executable, "forensic_main.py", "--no-bin"],
                        capture_output=False)
if result.returncode != 0:
    print("    [WARN] forensic_main.py exited with non-zero status — continuing anyway.")

# ── 3. Run extract_blob_convs.py ──────────────────────────────────────────────
print("\n[3] Running extract_blob_convs.py (IndexedDB blobs)...")
subprocess.run([sys.executable, "extract_blob_convs.py"], capture_output=False)

# ── 4. Merge curated back ─────────────────────────────────────────────────────
print("\n[4] Merging curated items back...")
with open(OUT, "r", encoding="utf-8") as f:
    fresh = json.load(f)

items = fresh.get("items", [])

# Build a set of (conversation_id, message_id) pairs already in fresh output
existing_keys = set()
for x in items:
    cid = x.get("conversation_id", "")
    mid = x.get("payload", {}).get("message_id", "")
    existing_keys.add((cid, mid))

added = 0
for item in curated:
    cid = item.get("conversation_id", "")
    mid = item.get("payload", {}).get("message_id", "")
    # Skip noise sources even from curated set
    if cid in ("deleted_fragment_pool", "claude_account_metadata"):
        continue
    if (cid, mid) not in existing_keys:
        items.append(item)
        existing_keys.add((cid, mid))
        added += 1

print(f"    Added {added} curated items not found in fresh extraction.")

# ── 5. Strip noise ────────────────────────────────────────────────────────────
before = len(items)
items = [x for x in items
         if x.get("conversation_id") not in ("deleted_fragment_pool", "claude_account_metadata")]
# Remove truncated partial blob_26 duplicates
partial_titles = {"ting data from LLMs!", "s generative AI"}
items = [x for x in items if x.get("title") not in partial_titles]
print(f"[5] Removed {before - len(items)} noise/duplicate items.")

# ── 6. Sort and save ──────────────────────────────────────────────────────────
items.sort(key=lambda x: float(x.get("update_time") or 0.0), reverse=True)
fresh["items"] = items

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(fresh, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Final output: {len(items)} items -> {OUT}")
print("Titles recovered:")
seen = set()
for x in items:
    t = x.get("title", "(no title)")
    if t not in seen:
        print(f"  • {t}")
        seen.add(t)

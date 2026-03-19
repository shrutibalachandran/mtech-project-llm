"""
ldb_full_carve.py  –  Full binary carve of ALL ChatGPT LevelDB files.

Scans every .ldb (SSTable) and .log (WAL) file across all candidate
directories, extracting:
  • conversation_id  (UUID pattern)
  • title            (from "title":"..." fragment)
  • create_time / update_time  (if present nearby)

Produces a merged TSV + JSON, then compares against the existing
RECOVERED_CHATGPT_HISTORY.json to show what is MISSING.
"""

import os
import re
import json
import struct
import glob

BASE = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"

# ── directories to scan ───────────────────────────────────────────────────────
SCAN_DIRS = [
    os.path.join(BASE, "temp_live_ldb"),
    os.path.join(BASE, "temp_diag_ldb"),
    os.path.join(BASE, "temp_live_idb"),
    os.path.join(BASE, "temp_diag_f"),
    os.path.join(BASE, "temp_diag_f_v2"),
]

EXISTING_JSON = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")
OUT_JSON      = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")  # we'll UPDATE this

# UUID pattern
UUID_RE = re.compile(
    rb"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I
)

# title pattern (JSON fragment) – greedy up to 300 chars
TITLE_RE = re.compile(
    rb'"title"\s*:\s*"((?:[^"\\]|\\.){1,300})"',
    re.S
)

# create_time / update_time
CREATE_RE = re.compile(rb'"create_time"\s*:\s*([\d.]+)')
UPDATE_RE = re.compile(rb'"update_time"\s*:\s*([\d.]+)')


def read_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        print(f"  [WARN] Cannot read {path}: {e}")
        return b""


def decode_title(raw_bytes):
    """Decode escaped JSON title bytes."""
    try:
        # Wrap so json.loads can handle backslash escapes
        return json.loads(b'"' + raw_bytes + b'"')
    except Exception:
        try:
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return repr(raw_bytes)


def carve_file(path):
    """
    Carve a binary file for (conversation_id, title, update_time) triples.
    Strategy: find every title occurrence, then look ±2KB around it for a UUID
    that looks like a conversation_id.
    """
    data = read_file(path)
    if not data:
        return []

    results = []
    # Find all title positions
    for tm in TITLE_RE.finditer(data):
        title_bytes = tm.group(1)
        title = decode_title(title_bytes)

        # Skip blank / junk titles
        if not title or len(title) < 2:
            continue
        if title.lower().startswith("new chat") and len(title) < 10:
            pass  # keep "New chat" – it could be a real entry

        # Surrounding window ±3 KB
        win_start = max(0, tm.start() - 3000)
        win_end   = min(len(data), tm.end() + 3000)
        window    = data[win_start:win_end]

        # Find UUIDs in the window
        uuids = UUID_RE.findall(window)
        cid = uuids[0].decode("ascii").lower() if uuids else ""

        # Find update_time near this title
        um = UPDATE_RE.search(window)
        update_time = float(um.group(1)) if um else 0.0

        cm = CREATE_RE.search(window)
        create_time = float(cm.group(1)) if cm else 0.0

        results.append({
            "conversation_id": cid,
            "title": title,
            "update_time": update_time,
            "create_time": create_time,
            "source_file": os.path.basename(path),
        })

    return results


# ── scan all directories ──────────────────────────────────────────────────────
all_carved = []
for d in SCAN_DIRS:
    if not os.path.isdir(d):
        continue
    files = (
        glob.glob(os.path.join(d, "*.ldb")) +
        glob.glob(os.path.join(d, "*.log")) +
        glob.glob(os.path.join(d, "*.bin")) +
        glob.glob(os.path.join(d, "*.sst"))
    )
    for fpath in files:
        hits = carve_file(fpath)
        if hits:
            print(f"  {os.path.basename(fpath)}: {len(hits)} hits")
        all_carved.extend(hits)

# Also carve the main-directory .bin files from cache recovery
for fpath in glob.glob(os.path.join(BASE, "recovered_br_f_*.bin")):
    hits = carve_file(fpath)
    all_carved.extend(hits)

print(f"\n[INFO] Total carved entries (raw): {len(all_carved)}")

# ── also grab ACTIVE_TITLES_UTF8.txt as title-only entries ───────────────────
active_titles_path = os.path.join(BASE, "ACTIVE_TITLES_UTF8.txt")
title_only_set = set()
if os.path.exists(active_titles_path):
    with open(active_titles_path, encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t:
                title_only_set.add(t)

# also from DEEP_RECOVERED_CONVERSATIONS.json
deep_path = os.path.join(BASE, "DEEP_RECOVERED_CONVERSATIONS.json")
deep_entries = []
if os.path.exists(deep_path):
    with open(deep_path, encoding="utf-8") as f:
        deep_entries = json.load(f)
    for e in deep_entries:
        title_only_set.add(e.get("title", ""))

# also from HARVESTED_CIDS.json if it has titles
harvested_path = os.path.join(BASE, "HARVESTED_CIDS.json")
harvested = []
if os.path.exists(harvested_path):
    with open(harvested_path, encoding="utf-8") as f:
        try:
            harvested = json.load(f)
        except Exception:
            pass
    for e in (harvested if isinstance(harvested, list) else []):
        t = e.get("title", "") if isinstance(e, dict) else ""
        if t:
            title_only_set.add(t)
            if e.get("conversation_id"):
                all_carved.append({
                    "conversation_id": e["conversation_id"],
                    "title": t,
                    "update_time": e.get("update_time", 0.0),
                    "create_time": e.get("create_time", 0.0),
                    "source_file": "HARVESTED_CIDS.json",
                })

print(f"[INFO] Active titles set: {len(title_only_set)}")

# ── load existing RECOVERED_CHATGPT_HISTORY.json ──────────────────────────────
with open(EXISTING_JSON, encoding="utf-8") as f:
    existing = json.load(f)
existing_items = existing.get("items", [])
existing_cids  = {i["conversation_id"] for i in existing_items}
existing_titles = {i["title"] for i in existing_items}

print(f"[INFO] Existing recovered: {len(existing_items)} conversations")

# ── deduplicate carved entries ────────────────────────────────────────────────
# by conversation_id: keep the one with the highest update_time
by_cid = {}
for e in all_carved:
    cid = e["conversation_id"]
    if not cid or cid == "00000000-0000-0000-0000-000000000000":
        continue
    if cid not in by_cid or e["update_time"] > by_cid[cid]["update_time"]:
        by_cid[cid] = e

# ── find genuinely NEW conversation_ids not yet in the recovered file ─────────
new_cid_entries = []
for cid, e in by_cid.items():
    if cid not in existing_cids:
        new_cid_entries.append(e)

# ── find titles in ACTIVE_TITLES that are missing from recovered ──────────────
missing_titles = title_only_set - existing_titles
print(f"\n[RESULT] New conversation_ids found in LDB:  {len(new_cid_entries)}")
print(f"[RESULT] Titles in ACTIVE list but missing:   {len(missing_titles)}")

if new_cid_entries:
    print("\n--- New conversation_id entries from LDB ---")
    for e in sorted(new_cid_entries, key=lambda x: x["update_time"], reverse=True):
        print(f"  {e['conversation_id']}  |  {e['title']!r}  |  upd={e['update_time']}  |  src={e['source_file']}")

if missing_titles:
    print("\n--- Titles present in ACTIVE_TITLES but missing from recovered output ---")
    for t in sorted(missing_titles):
        print(f"  {t!r}")

# ── build new items to add ───────────────────────────────────────────────────
from datetime import datetime, timezone

def ts_to_iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return "1970-01-01T00:00:00Z"

new_items = []

# 1. From carved LDB entries with a real conversation_id not yet in file
for e in new_cid_entries:
    iso = ts_to_iso(e["update_time"])
    snip = f"[No cached content] updated={iso}" if not e.get("snippet") else e["snippet"]
    new_items.append({
        "conversation_id": e["conversation_id"],
        "current_node_id": "",
        "title": e["title"],
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "update_time": e["update_time"],
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": snip,
        },
        "source_file": e["source_file"],
        "recovery_note": "Recovered from LevelDB binary carve",
    })

# 2. From missing titles (title-only, no CID known)
for t in missing_titles:
    new_items.append({
        "conversation_id": "",
        "current_node_id": "",
        "title": t,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "update_time": 0.0,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": "[No cached content] – title recovered from LevelDB active titles index",
        },
        "source_file": "ACTIVE_TITLES_UTF8.txt",
        "recovery_note": "Title-only: recovered from LevelDB active titles index; no conversation_id available",
    })

# ── merge into existing list and re-sort ─────────────────────────────────────
combined = existing_items + new_items
combined.sort(key=lambda x: float(x.get("update_time") or 0), reverse=True)

print(f"\n[INFO] Adding {len(new_items)} new entries")
print(f"[INFO] Total after merge: {len(combined)}")

# ── write updated output ──────────────────────────────────────────────────────
output = {
    "_forensic_notes": existing.get("_forensic_notes", ""),
    "_recovery_additions": f"{len(new_items)} additional entries recovered from LevelDB binary carving and active title index on second pass.",
    "items": combined,
}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Updated: {OUT_JSON}")
print(f"       Before: {len(existing_items)} | After: {len(combined)} | Added: {len(new_items)}")

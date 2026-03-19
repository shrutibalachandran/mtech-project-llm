"""
merge_all_chatgpt.py  –  Final comprehensive merge of ALL ChatGPT conversation data.

Sources used (in priority order):
  1. RECOVERED_CHATGPT_HISTORY.json   – existing 390 entries with real content
  2. HARVESTED_CIDS.json              – conversation_id + title + timestamps
  3. ORPHANED_CID_DETAILS.json        – orphaned conversation entries
  4. ALL_FORENSIC_TITLES.json         – 200+ titles from cache forensics 
  5. ACTIVE_TITLES_UTF8.txt           – 143 titles from LDB active index
  6. DEEP_RECOVERED_CONVERSATIONS.json– 4 entries with mapping data
  7. temp_live_ldb / temp_diag_ldb    – WAL log raw text carve (for deleted convs)

For each source, we extract (conversation_id, title, update_time) and merge
into the final file. Missing conversations get [No cached content] placeholders.
Deleted conversations are flagged with is_deleted: true.
"""

import os
import re
import json
import struct
from datetime import datetime, timezone

BASE = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
OUT  = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")

UUID_RE   = re.compile(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
TITLE_RE  = re.compile(r'"title"\s*:\s*"((?:[^"\\]|\\.){1,300})"')
UPDATE_RE = re.compile(r'"update_time"\s*:\s*([\d.]+)')
CREATE_RE = re.compile(r'"create_time"\s*:\s*([\d.]+)')

def ts_to_iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return "1970-01-01T00:00:00Z"

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  [WARN] Cannot load {path}: {e}")
        return None

# ─── Master dict keyed by conversation_id ─────────────────────────────────────
# Entry: { cid: { title, update_time, create_time, snippet, source, is_deleted } }
master = {}

# Title-only entries (no CID): stored separately
title_only = {}  # title -> { source }

def upsert(cid, title, update_time=0.0, create_time=0.0,
           snippet=None, source="", is_deleted=False):
    """Insert or update an entry. Higher update_time wins for same CID."""
    cid = (cid or "").strip().lower()
    title = (title or "").strip()
    if not title or len(title) < 2:
        return
    if not cid or cid == "00000000-0000-0000-0000-000000000000":
        # title-only
        if title not in title_only:
            title_only[title] = {"source": source}
        return
    update_time = float(update_time or 0)
    create_time = float(create_time or 0)
    prev = master.get(cid)
    if prev is None or update_time > prev["update_time"]:
        master[cid] = {
            "title":       title,
            "update_time": update_time,
            "create_time": create_time,
            "snippet":     snippet,
            "source":      source,
            "is_deleted":  is_deleted,
        }

# ─── Source 1: Existing RECOVERED_CHATGPT_HISTORY.json ────────────────────────
existing_data = load_json(OUT)
existing_items = existing_data.get("items", []) if existing_data else []
for item in existing_items:
    cid     = item.get("conversation_id", "")
    title   = item.get("title", "")
    ut      = item.get("update_time", 0.0)
    ct      = 0.0
    snip    = item.get("payload", {}).get("snippet", "")
    src     = item.get("source_file", "cache")
    is_del  = item.get("is_deleted", False)
    upsert(cid, title, ut, ct, snip, src, is_del)
print(f"[S1] Existing RECOVERED_CHATGPT_HISTORY.json: {len(existing_items)} items loaded")

# ─── Source 2: HARVESTED_CIDS.json ────────────────────────────────────────────
harvested = load_json(os.path.join(BASE, "HARVESTED_CIDS.json"))
h_count = 0
if isinstance(harvested, list):
    for e in harvested:
        if not isinstance(e, dict):
            continue
        cid   = e.get("conversation_id", "")
        title = e.get("title", "")
        ut    = e.get("update_time", 0.0)
        ct    = e.get("create_time", 0.0)
        snip  = e.get("snippet") or e.get("last_message", "")
        src   = e.get("source", "HARVESTED_CIDS.json")
        is_del = e.get("is_deleted", False) or e.get("deleted", False)
        upsert(cid, title, ut, ct, snip, src, is_del)
        h_count += 1
elif isinstance(harvested, dict):
    for cid, e in harvested.items():
        if not isinstance(e, dict):
            continue
        title = e.get("title", "")
        ut    = e.get("update_time", 0.0)
        ct    = e.get("create_time", 0.0)
        snip  = e.get("snippet", "")
        is_del = e.get("is_deleted", False) or e.get("deleted", False)
        upsert(cid, title, ut, ct, snip, "HARVESTED_CIDS.json", is_del)
        h_count += 1
print(f"[S2] HARVESTED_CIDS.json: {h_count} entries processed")

# ─── Source 3: ORPHANED_CID_DETAILS.json ──────────────────────────────────────
orphaned = load_json(os.path.join(BASE, "ORPHANED_CID_DETAILS.json"))
o_count = 0
if isinstance(orphaned, list):
    for e in orphaned:
        if not isinstance(e, dict):
            continue
        cid   = e.get("conversation_id", "")
        title = e.get("title", "")
        ut    = e.get("update_time", 0.0)
        ct    = e.get("create_time", 0.0)
        snip  = e.get("snippet", "")
        is_del = e.get("is_deleted", True)  # orphaned = likely deleted
        if cid and title:
            upsert(cid, title, ut, ct, snip, "ORPHANED_CID_DETAILS.json", is_del)
            o_count += 1
elif isinstance(orphaned, dict):
    for cid, sub in orphaned.items():
        if not isinstance(sub, dict):
            continue
        title = sub.get("title", "")
        ut    = sub.get("update_time", 0.0)
        ct    = sub.get("create_time", 0.0)
        snip  = sub.get("snippet", "") or sub.get("text", "")
        is_del = sub.get("is_deleted", True)
        if title:
            upsert(cid, title, ut, ct, snip, "ORPHANED_CID_DETAILS.json", is_del)
            o_count += 1
print(f"[S3] ORPHANED_CID_DETAILS.json: {o_count} entries processed")

# ─── Source 4: ALL_FORENSIC_TITLES.json ───────────────────────────────────────
all_titles = load_json(os.path.join(BASE, "ALL_FORENSIC_TITLES.json"))
t_count = 0
if isinstance(all_titles, list):
    for entry in all_titles:
        if isinstance(entry, list) and len(entry) >= 1:
            title = str(entry[0]).strip()
            src_d = entry[1] if len(entry) > 1 else {}
            src = src_d.get("source", "ALL_FORENSIC_TITLES.json") if isinstance(src_d, dict) else "ALL_FORENSIC_TITLES.json"
            if title:
                upsert("", title, 0.0, 0.0, None, src)
                t_count += 1
        elif isinstance(entry, dict):
            title = entry.get("title", "")
            cid   = entry.get("conversation_id", "")
            ut    = entry.get("update_time", 0.0)
            ct    = entry.get("create_time", 0.0)
            src   = entry.get("source", "ALL_FORENSIC_TITLES.json")
            if title:
                upsert(cid, title, ut, ct, None, src)
                t_count += 1
print(f"[S4] ALL_FORENSIC_TITLES.json: {t_count} entries processed")

# ─── Source 5: ACTIVE_TITLES_UTF8.txt ─────────────────────────────────────────
act_path = os.path.join(BASE, "ACTIVE_TITLES_UTF8.txt")
a_count = 0
if os.path.exists(act_path):
    with open(act_path, encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t:
                upsert("", t, 0.0, 0.0, None, "ACTIVE_TITLES_UTF8.txt")
                a_count += 1
print(f"[S5] ACTIVE_TITLES_UTF8.txt: {a_count} entries processed")

# ─── Source 6: DEEP_RECOVERED_CONVERSATIONS.json ──────────────────────────────
deep = load_json(os.path.join(BASE, "DEEP_RECOVERED_CONVERSATIONS.json"))
d_count = 0
if isinstance(deep, list):
    for e in deep:
        cid   = e.get("conversation_id", "")
        title = e.get("title", "")
        ut    = e.get("update_time", 0.0)
        ct    = e.get("create_time", 0.0)
        snip  = e.get("snippet", "")[:200] if e.get("snippet") else ""
        src   = e.get("source", "DEEP_RECOVERED_CONVERSATIONS.json")
        if title:
            upsert(cid, title, ut, ct, snip, src)
            d_count += 1
print(f"[S6] DEEP_RECOVERED_CONVERSATIONS.json: {d_count} entries processed")

# ─── Source 7: WAL log raw text carve (.log files) ────────────────────────────
# Read the raw bytes of each WAL file and scan for title/UUID text fragments.
WAL_DIRS = [
    os.path.join(BASE, "temp_live_ldb"),
    os.path.join(BASE, "temp_diag_ldb"),
]
import glob, shutil

w_count = 0
for d in WAL_DIRS:
    for fpath in glob.glob(os.path.join(d, "*.log")) + glob.glob(os.path.join(d, "*.ldb")):
        try:
            with open(fpath, "rb") as f:
                raw = f.read()
            # Decode with errors=replace so we can regex over it
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        # Find all title occurrences
        for tm in TITLE_RE.finditer(text):
            title = tm.group(1)
            if not title or len(title) < 2:
                continue
            # look ±3KB for UUID and timestamps
            win = text[max(0, tm.start()-3000):tm.end()+3000]
            uuid_m = UUID_RE.search(win)
            cid = uuid_m.group(1).lower() if uuid_m else ""
            upd_m = UPDATE_RE.search(win)
            ut = float(upd_m.group(1)) if upd_m else 0.0
            cre_m = CREATE_RE.search(win)
            ct = float(cre_m.group(1)) if cre_m else 0.0
            upsert(cid, title, ut, ct, None, os.path.basename(fpath))
            w_count += 1

print(f"[S7] WAL/LDB raw text carve: {w_count} fragments processed")

# ─── Now merge CID-keyed master with title-only ────────────────────────────────
#
# For title-only entries: if a CID entry already has this title, skip it.
# Otherwise add as placeholder entry.
#
existing_cid_titles = {v["title"] for v in master.values()}
title_only_new = {t: s for t, s in title_only.items()
                  if t not in existing_cid_titles
                  and t not in {"", "New chat", "What is 5", "What is apple", "Student"}}
print(f"\n[INFO] CID-keyed conversations: {len(master)}")
print(f"[INFO] Title-only (no CID):      {len(title_only_new)}")

# ─── Build output items ────────────────────────────────────────────────────────
out_items = []

# 1. CID-keyed entries
for cid, e in master.items():
    title   = e["title"]
    ut      = e["update_time"]
    iso     = ts_to_iso(ut)
    snip    = e["snippet"]
    is_del  = e["is_deleted"]
    src     = e["source"]

    if snip and not snip.startswith("[No cached content]"):
        clean_snip = snip
    else:
        if is_del:
            clean_snip = f"[Deleted conversation] title={title!r} updated={iso}"
        else:
            clean_snip = f"[No cached content] updated={iso}"

    item = {
        "conversation_id": cid,
        "current_node_id": "",
        "title": title,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "is_deleted": is_del,
        "update_time": ut,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": clean_snip,
        },
        "source_file": src,
    }
    out_items.append(item)

# 2. Title-only entries
for title, meta in title_only_new.items():
    item = {
        "conversation_id": "",
        "current_node_id": "",
        "title": title,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "is_deleted": False,
        "update_time": 0.0,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": "[No cached content] – title recovered from forensic index; no conversation_id available",
        },
        "source_file": meta["source"],
        "recovery_note": "Title-only: conversation_id not recoverable",
    }
    out_items.append(item)

# Sort: entries with real timestamps first (newest→oldest), then title-only at end
out_items.sort(key=lambda x: float(x.get("update_time") or 0), reverse=True)

# ─── Compute stats ─────────────────────────────────────────────────────────────
total        = len(out_items)
deleted_count = sum(1 for i in out_items if i.get("is_deleted"))
placeholder   = sum(1 for i in out_items if i["payload"]["snippet"].startswith("[No cached content]")
                    or i["payload"]["snippet"].startswith("[Deleted"))
with_content  = total - placeholder

print(f"\n[RESULT] Total conversations: {total}")
print(f"         With real content:   {with_content}")
print(f"         Placeholder/deleted: {placeholder}")
print(f"         Flagged as deleted:  {deleted_count}")

# ─── Write output ──────────────────────────────────────────────────────────────
output = {
    "_forensic_notes": (
        "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data physically "
        "recovered from binary artifacts. No AI text generation or falsification used."
    ),
    "_recovery_additions": (
        f"Merged from 7 sources: existing cache, HARVESTED_CIDS, ORPHANED_CID_DETAILS, "
        f"ALL_FORENSIC_TITLES, ACTIVE_TITLES, DEEP_RECOVERED_CONVERSATIONS, WAL log carve. "
        f"Total: {total} unique conversations."
    ),
    "items": out_items,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n[DONE] Written to: {OUT}")
print(f"       {total} total conversations (before: {len(existing_items)})")
print(f"       Added: {total - len(existing_items)} new entries")

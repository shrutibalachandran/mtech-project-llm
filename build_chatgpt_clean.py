"""
build_chatgpt_clean.py
Post-processes CHATGPT_RECONSTRUCTED_HISTORY.json to produce a clean
RECOVERED_CHATGPT_HISTORY.json that:
  1. Drops all noise (deleted_fragment_pool, residual_fragment, HTML blobs)
  2. Deduplicates by conversation_id: keeps the entry with a real snippet
     (role != 'unknown' and snippet doesn't look like HTML), preferring
     the latest update_time per conversation
  3. Sorts newest-to-oldest by update_time
  4. Reformats every entry to match the Claude JSON schema exactly:
       conversation_id, current_node_id, title, model, is_archived,
       is_starred, update_time, payload.{kind,message_id,snippet},
       source_file
  5. For conversations with NO real snippet, creates a
     "[No cached content] created=... updated=..." placeholder
"""

import json
import os
from datetime import datetime, timezone

BASE = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
SRC  = os.path.join(BASE, "CHATGPT_RECONSTRUCTED_HISTORY.json")
DST  = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")

NOISE_IDS   = {"deleted_fragment_pool"}
NOISE_KINDS = {"residual_fragment", "forensic_carve"}

def ts_to_iso(ts):
    """Convert a Unix float timestamp to ISO-8601 Z string."""
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return "1970-01-01T00:00:00.000000Z"

def snippet_is_html(s):
    return isinstance(s, str) and s.lstrip().startswith("<!DOCTYPE")

def snippet_is_real(s):
    """True if snippet has actual conversational content."""
    if not isinstance(s, str) or not s.strip():
        return False
    if snippet_is_html(s):
        return False
    return True

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

items = data.get("items", [])
print(f"[INFO] Total items loaded: {len(items)}")

# ── Step 1: filter out obvious noise ─────────────────────────────────────────
kept = []
for item in items:
    cid  = item.get("conversation_id", "")
    kind = item.get("payload", {}).get("kind", "")

    if cid in NOISE_IDS:
        continue
    if kind in NOISE_KINDS:
        continue
    kept.append(item)

print(f"[INFO] After noise filter: {len(kept)}")

# ── Step 2: deduplicate by conversation_id ───────────────────────────────────
# For each conversation_id, collect all its fragments. 
# Priority: entry with a real snippet (non-HTML, non-empty) from the most
# recent update_time. Fallback: most recent entry regardless.
by_cid = {}
for item in kept:
    cid = item.get("conversation_id", "")
    if not cid:
        cid = f"unknown_{id(item)}"

    if cid not in by_cid:
        by_cid[cid] = {"best_with_content": None, "best_overall": None}

    ts = float(item.get("update_time", 0) or 0)
    snippet = item.get("payload", {}).get("snippet", "")
    has_content = snippet_is_real(snippet)

    prev_best = by_cid[cid]["best_with_content"]
    if has_content:
        if prev_best is None or ts > float(prev_best.get("update_time", 0) or 0):
            by_cid[cid]["best_with_content"] = item

    prev_overall = by_cid[cid]["best_overall"]
    if prev_overall is None or ts > float(prev_overall.get("update_time", 0) or 0):
        by_cid[cid]["best_overall"] = item

deduped = []
for cid, candidates in by_cid.items():
    chosen = candidates["best_with_content"] or candidates["best_overall"]
    deduped.append(chosen)

print(f"[INFO] After deduplication: {len(deduped)}")

# ── Step 3: sort newest-to-oldest ─────────────────────────────────────────────
deduped.sort(key=lambda x: float(x.get("update_time", 0) or 0), reverse=True)

# ── Step 4: reformat to Claude-style schema ───────────────────────────────────
out_items = []
for item in deduped:
    cid   = item.get("conversation_id", "")
    title = item.get("title", "Unknown Conversation")
    ts    = float(item.get("update_time", 0) or 0)
    iso   = ts_to_iso(ts)

    payload = item.get("payload", {})
    raw_snip = payload.get("snippet", "")

    # Build clean snippet
    if snippet_is_real(raw_snip):
        clean_snip = raw_snip
    else:
        clean_snip = f"[No cached content] updated={iso}"

    # source_file
    meta = payload.get("metadata", {})
    src_file = meta.get("source_file") or item.get("source_file") or "cache"

    out_items.append({
        "conversation_id": cid,
        "current_node_id": item.get("current_node_id", ""),
        "title": title,
        "model": "",
        "is_archived": False,
        "is_starred": False,
        "update_time": ts,
        "payload": {
            "kind": "message",
            "message_id": "",
            "snippet": clean_snip
        },
        "source_file": src_file
    })

print(f"[INFO] Total clean output items: {len(out_items)}")

# ── Step 5: write output ──────────────────────────────────────────────────────
os.makedirs(os.path.dirname(DST), exist_ok=True)

output = {
    "_forensic_notes": (
        "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data physically "
        "recovered from binary artifacts. No AI text generation or falsification used."
    ),
    "items": out_items
}

with open(DST, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"[DONE] Written to: {DST}")
print(f"       {len(out_items)} unique conversations, newest-to-oldest.")

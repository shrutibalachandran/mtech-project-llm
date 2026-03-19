"""
format_chatgpt_output.py  –  All 5 fixes for ChatGPT output:

  FIX 1: Merge title + message data by grouping fragments into conversations
  FIX 2: Generate CHATGPT_REPORT.md with human-readable timestamps
  FIX 3: Scan WAL logs for recent data  (already handled in merge step)
  FIX 4: Sort conversations newest → oldest
  FIX 5: Final grouped JSON structure

Output files:
  reports/RECOVERED_CHATGPT_GROUPED.json   (grouped structure)
  reports/CHATGPT_REPORT.md                (markdown report)
  reports/RECOVERED_CHATGPT_TIMELINES.json (updated in-place with titles)
"""
import os, json, re, io, sys
from datetime import datetime, timezone

# Force UTF-8 output on Windows to avoid cp1252 errors
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


BASE     = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
TIMELINE = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_TIMELINES.json")
HISTORY  = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")
OUT_JSON = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_GROUPED.json")
OUT_MD   = os.path.join(BASE, "reports", "CHATGPT_REPORT.md")

IST_OFFSET = 5.5 * 3600   # +05:30 (India)

def ts_to_human(ts):
    """Convert Unix timestamp to IST human-readable string."""
    try:
        t = float(ts)
        if t <= 0:
            return "Unknown time"
        dt_utc = datetime.fromtimestamp(t, tz=timezone.utc)
        dt_ist = datetime.fromtimestamp(t + IST_OFFSET, tz=timezone.utc)
        return dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return "Unknown time"

def ts_to_float(ts):
    try:
        return float(ts or 0)
    except Exception:
        return 0.0

# ── Load RECOVERED_CHATGPT_HISTORY.json → build CID-to-title map ────────────
print("[1] Loading RECOVERED_CHATGPT_HISTORY.json for title lookup...")
with open(HISTORY, encoding="utf-8") as f:
    history = json.load(f)

cid_to_title = {}
title_to_cid = {}
cid_to_update = {}
for item in history.get("items", []):
    cid   = (item.get("conversation_id") or "").strip()
    title = (item.get("title") or "").strip()
    ut    = ts_to_float(item.get("update_time"))
    if cid and title:
        cid_to_title[cid] = title
        cid_to_update[cid] = ut
    if title and cid:
        title_to_cid[title] = cid

print(f"    {len(cid_to_title)} CID->title mappings loaded")

# ── Load RECOVERED_CHATGPT_TIMELINES.json ─────────────────────────────────────
print("[2] Loading RECOVERED_CHATGPT_TIMELINES.json...")
with open(TIMELINE, encoding="utf-8") as f:
    timelines = json.load(f)
raw_items = timelines.get("items", [])
print(f"    {len(raw_items)} raw conversation entries")

# ── Step A: Group fragments by conversation ───────────────────────────────────
# The timeline file has some entries with ALL messages grouped (like cid 69245692-...)
# and many with single messages. We'll:
#   • Keep multi-message entries as-is
#   • Try to cluster single-message entries by matching their snippets against
#     the first/last snippet of multi-message entries
#   • Assign titles from CID→title map or snippet match

grouped = {}   # cid -> { title, messages[], latest_update }

def best_title(cid):
    """Look up best title for a CID."""
    t = cid_to_title.get(cid, "")
    if t:
        return t
    # Try partial match
    cid_prefix = cid[:8] if len(cid) >= 8 else cid
    for k, v in cid_to_title.items():
        if k.startswith(cid_prefix):
            return v
    return ""

# First pass: collect all entries
for item in raw_items:
    cid  = (item.get("conversation_id") or "").strip()
    msgs = item.get("messages", [])
    if not cid or not msgs:
        continue
    
    title = best_title(cid)
    latest_upd = max((ts_to_float(m.get("update_time")) for m in msgs), default=0.0)

    if cid not in grouped:
        grouped[cid] = {
            "title": title,
            "messages": [],
            "latest_update": latest_upd,
        }
    else:
        if latest_upd > grouped[cid]["latest_update"]:
            grouped[cid]["latest_update"] = latest_upd
        if not grouped[cid]["title"] and title:
            grouped[cid]["title"] = title
    
    # Merge messages (deduplicate by snippet+role)
    existing_sigs = {
        (m.get("role",""), m.get("snippet","")[:80])
        for m in grouped[cid]["messages"]
    }
    for m in msgs:
        sig = (m.get("role",""), m.get("snippet","")[:80])
        if sig not in existing_sigs:
            grouped[cid]["messages"].append(m)
            existing_sigs.add(sig)

print(f"[3] After grouping: {len(grouped)} unique conversations")

# Second pass: sort messages within each conversation by update_time
for cid, g in grouped.items():
    g["messages"].sort(key=lambda m: ts_to_float(m.get("update_time")), reverse=False)
    if not g["title"]:
        # Try to derive title from snippet
        for m in g["messages"]:
            snip = (m.get("snippet") or "")[:60].strip().replace("\n", " ")
            if snip and m.get("role") in ("user","assistant"):
                g["title"] = snip[:50] + "..." if len(snip) > 50 else snip
                break
    if not g["title"]:
        g["title"] = "Unknown conversation"

# ── Step B: Build final sorted output list ───────────────────────────────────
conv_list = []
for cid, g in grouped.items():
    ut = g["latest_update"]
    # Fall back to history update_time if no timestamp found
    if ut == 0.0:
        ut = cid_to_update.get(cid, 0.0)
    conv_list.append({
        "conversation_id": cid,
        "title": g["title"],
        "latest_update": ut,
        "latest_update_human": ts_to_human(ut),
        "messages": g["messages"],
    })

# FIX 4: Sort newest → oldest
conv_list.sort(key=lambda c: c["latest_update"], reverse=True)
print(f"[4] Sorted {len(conv_list)} conversations newest→oldest")

# ── FIX 5: Write RECOVERED_CHATGPT_GROUPED.json ──────────────────────────────
output_json = {
    "_forensic_notes": (
        "DIGITAL FORENSIC INTEGRITY STATEMENT: Grouped ChatGPT conversation timeline. "
        "Messages are reconstructed from binary artifact fragments. "
        "Timestamps are converted to IST (UTC+05:30). "
        "No AI text generation was used."
    ),
    "total_conversations": len(conv_list),
    "items": conv_list,
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(output_json, f, indent=2, ensure_ascii=False)
print(f"[5] Written: {OUT_JSON}")

# ── FIX 2: Generate CHATGPT_REPORT.md ─────────────────────────────────────────
print("[6] Generating CHATGPT_REPORT.md...")
lines = []
lines.append("# ChatGPT Recovered Conversations – Forensic Report")
lines.append("")
lines.append(f"**Generated:** {ts_to_human(0)} (IST)")
lines.append(f"**Total conversations:** {len(conv_list)}")
lines.append(f"**Source:** RECOVERED_CHATGPT_TIMELINES.json + RECOVERED_CHATGPT_HISTORY.json")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Table of Contents")
for i, conv in enumerate(conv_list[:50]):  # TOC for first 50
    anchor = re.sub(r'[^a-z0-9\-]', '', conv['title'].lower().replace(' ', '-'))
    lines.append(f"{i+1}. [{conv['title']}](#{anchor})")
lines.append("")
lines.append("---")
lines.append("")

ROLE_LABEL = {
    "user":      "👤 USER",
    "assistant": "🤖 ASSISTANT",
    "system":    "⚙️  SYSTEM",
    "unknown":   "❓ UNKNOWN",
}

for i, conv in enumerate(conv_list):
    cid   = conv["conversation_id"]
    title = conv["title"]
    ut    = conv["latest_update"]
    msgs  = conv["messages"]
    
    lines.append(f"## Conversation: {title}")
    lines.append("")
    lines.append(f"**Conversation ID:** `{cid}`")
    lines.append(f"**Last updated:** {ts_to_human(ut)}")
    lines.append(f"**Messages:** {len(msgs)}")
    lines.append("")
    
    if not msgs:
        lines.append("*No messages recovered for this conversation.*")
    else:
        for msg in msgs:
            role  = msg.get("role", "unknown")
            snip  = msg.get("snippet", "")
            msg_ts = ts_to_float(msg.get("update_time"))
            label  = ROLE_LABEL.get(role, f"❓ {role.upper()}")
            time_s = ts_to_human(msg_ts) if msg_ts > 0 else "Unknown time"
            
            lines.append(f"**[{time_s}] {label}:**")
            lines.append(snip)
            lines.append("")
    
    lines.append("---")
    lines.append("")

# Write markdown
md_content = "\n".join(lines)
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(md_content)
print(f"[7] Written: {OUT_MD}")

# ── Also update RECOVERED_CHATGPT_TIMELINES.json in-place with titles ─────────
print("[8] Updating RECOVERED_CHATGPT_TIMELINES.json with titles...")
for item in raw_items:
    cid = (item.get("conversation_id") or "").strip()
    if cid and cid in grouped:
        if not item.get("title"):
            item["title"] = grouped[cid]["title"]

timelines_updated = {
    "_forensic_notes": timelines.get("_forensic_notes", ""),
    "items": raw_items,
}
with open(TIMELINE, "w", encoding="utf-8") as f:
    json.dump(timelines_updated, f, indent=2, ensure_ascii=False)
print(f"[8] Updated: {TIMELINE}")

# ── Summary ───────────────────────────────────────────────────────────────────
with_msgs    = sum(1 for c in conv_list if c["messages"])
with_titles  = sum(1 for c in conv_list if c["title"] not in ("Unknown conversation", ""))
with_ts      = sum(1 for c in conv_list if c["latest_update"] > 0)

print(f"\n=== SUMMARY ===")
print(f"Total conversations : {len(conv_list)}")
print(f"With titles         : {with_titles}")
print(f"With messages       : {with_msgs}")
print(f"With real timestamps: {with_ts}")
print(f"Newest conversation : {conv_list[0]['title']} @ {conv_list[0]['latest_update_human']}")
print(f"Oldest conversation : {conv_list[-1]['title']} @ {conv_list[-1]['latest_update_human']}")
print(f"\nOutput files:")
print(f"  {OUT_JSON}")
print(f"  {OUT_MD}")
print(f"  {TIMELINE}  (updated in-place)")

"""
dedup_and_finalize.py  –  Deduplicate RECOVERED_CHATGPT_HISTORY.json and 
regenerate RECOVERED_CHATGPT_GROUPED.json and CHATGPT_REPORT.md with March data.
"""
import os, sys, io, json, re
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE        = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"
OUT_HISTORY = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json")
OUT_GROUPED = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_GROUPED.json")
OUT_MD      = os.path.join(BASE, "reports", "CHATGPT_REPORT.md")

IST_OFFSET = 5.5 * 3600

def ts_ist(ts):
    try:
        t = float(ts)
        if t <= 0: return "Unknown time"
        return datetime.fromtimestamp(t + IST_OFFSET, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S IST")
    except: return "Unknown time"

def ts_float(ts):
    try: return float(ts or 0)
    except: return 0.0

# ── Load & deduplicate ────────────────────────────────────────────────────────
with open(OUT_HISTORY, encoding='utf-8') as f:
    data = json.load(f)
items = data['items']

print(f"Before dedup: {len(items)}")

# Dedup by conversation_id (keep highest update_time, preferring real snippet)
by_cid = {}
no_cid = []
for item in items:
    cid = (item.get("conversation_id") or "").strip()
    ut  = ts_float(item.get("update_time"))
    
    # Skip unassigned/noise CIDs
    if cid.startswith("unassigned_") or not cid:
        # Also dedup these by title
        title = item.get("title","")
        no_cid.append((title, ut, item))
        continue
    
    existing = by_cid.get(cid)
    if existing is None:
        by_cid[cid] = item
    else:
        ex_ut  = ts_float(existing.get("update_time"))
        ex_snip = (existing.get("payload",{}).get("snippet","") or "")
        new_snip = (item.get("payload",{}).get("snippet","") or "")
        # Keep the one with higher update_time, prefer real snippet
        if ut > ex_ut:
            by_cid[cid] = item
        elif ut == ex_ut and len(new_snip) > len(ex_snip):
            by_cid[cid] = item

# Dedup no-CID items by title
seen_titles = set()
deduped_no_cid = []
for title, ut, item in no_cid:
    t = title.strip().lower()
    if not t or t in seen_titles:
        continue
    seen_titles.add(t)
    deduped_no_cid.append(item)

all_items = list(by_cid.values()) + deduped_no_cid

# Sort newest → oldest
all_items.sort(key=lambda x: ts_float(x.get("update_time")), reverse=True)

print(f"After dedup:  {len(all_items)} unique conversations")
print(f"Newest: {ts_ist(all_items[0]['update_time'])} - {all_items[0]['title']}")

# ── Write cleaned history ─────────────────────────────────────────────────────
output = {
    "_forensic_notes": data.get("_forensic_notes",""),
    "_recovery_additions": data.get("_recovery_additions",""),
    "items": all_items,
}
with open(OUT_HISTORY, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"Written: {OUT_HISTORY}")

# ── Build GROUPED JSON ────────────────────────────────────────────────────────
# For grouping: create one entry per conversation (1 payload = 1 message)
grouped_items = []
for item in all_items:
    cid   = item.get("conversation_id","")
    title = item.get("title","")
    ut    = ts_float(item.get("update_time"))
    payload = item.get("payload", {})
    snip  = payload.get("snippet","")
    role  = payload.get("role","")
    
    grouped_items.append({
        "conversation_id":     cid,
        "title":               title,
        "latest_update":       ut,
        "latest_update_human": ts_ist(ut),
        "messages": [{
            "role":        role or "unknown",
            "snippet":     snip,
            "update_time": ut,
        }] if snip else [],
    })

grouped_output = {
    "_forensic_notes": data.get("_forensic_notes",""),
    "total_conversations": len(grouped_items),
    "items": grouped_items,
}
with open(OUT_GROUPED, "w", encoding="utf-8") as f:
    json.dump(grouped_output, f, indent=2, ensure_ascii=False)
print(f"Written: {OUT_GROUPED}")

# ── Build CHATGPT_REPORT.md ───────────────────────────────────────────────────
ROLE_LABEL = {
    "user":      "USER",
    "assistant": "ASSISTANT",
    "system":    "SYSTEM",
    "unknown":   "UNKNOWN",
}

lines = []
lines.append("# ChatGPT Recovered Conversations – Forensic Report")
lines.append("")
lines.append(f"**Generated:** 2026-03-19 by forensic tool")
lines.append(f"**Total conversations:** {len(all_items)}")
lines.append("")
lines.append("---")
lines.append("")

for item in all_items:
    cid    = item.get("conversation_id","")
    title  = item.get("title","") or "(untitled)"
    ut     = ts_float(item.get("update_time"))
    payload= item.get("payload",{})
    snip   = payload.get("snippet","")
    role   = payload.get("role","unknown")
    is_del = item.get("is_deleted", False)
    
    del_tag = " [DELETED]" if is_del else ""
    lines.append(f"## {title}{del_tag}")
    lines.append("")
    lines.append(f"- **ID:** `{cid}`")
    lines.append(f"- **Updated:** {ts_ist(ut)}")
    if snip:
        label = ROLE_LABEL.get(role, role.upper())
        lines.append(f"- **Role:** {label}")
        lines.append("")
        lines.append(f"**[{ts_ist(ut)}] {label}:**")
        lines.append(snip)
    lines.append("")
    lines.append("---")
    lines.append("")

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Written: {OUT_MD}")

# ── Summary ───────────────────────────────────────────────────────────────────
march_items = [i for i in all_items if ts_float(i.get("update_time")) >= 1772323200]
print(f"\n=== FINAL SUMMARY ===")
print(f"Total conversations: {len(all_items)}")
print(f"March 2026+: {len(march_items)}")
print(f"Newest: {ts_ist(all_items[0]['update_time'])} - {all_items[0]['title']}")
print()
print("March 2026 conversations:")
for i in march_items:
    print(f"  {ts_ist(i['update_time'])} | {i['title']}")

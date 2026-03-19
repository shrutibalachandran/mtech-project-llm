"""
merge_max_chatgpt.py  (v4 – Claude-schema output)
──────────────────────────────────────────────────────────────────
Outputs chatgpt_history.json in the SAME SCHEMA as RECOVERED_CLAUDE_HISTORY.json:

  One entry per message:
  {
    "conversation_id": "...",        ← same for all msgs in same conversation
    "current_node_id": "...",        ← message_id (or empty if unknown)
    "title": "...",
    "model": "",
    "is_archived": false,
    "is_starred": false,
    "update_time": 1234567890.0,     ← Unix seconds (accurate per-conversation)
    "payload": {
      "kind": "message",
      "message_id": "...",
      "snippet": "actual text...",
      "role": "user" | "assistant"
    }
  }
"""
import json, sys, io, re, os
from datetime import datetime, timezone
from hashlib import md5

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
OLD  = os.path.join(BASE, 'reports', 'RECOVERED_CHATGPT_GROUPED.json')
NEW  = os.path.join(BASE, 'reports', 'chatgpt', 'chatgpt_history.json')
OUT  = NEW

IST = 5.5 * 3600

# ── Snippet quality gate ──────────────────────────────────────────────────────
_NOISE = [
    '[No cached content]', '{"conversation_id"', '}},' , '"title":',
    '"is_archived"', '"mapping"', '"current_node_id"', 'accountUserId',
    'id"$', 'client-created-root', '"kind":"message"', '"message_id"',
    '"snippet":', 'created=20', 'updated=20',
    'og:url', 'og:title', 'og:description', 'meta property',
    '<meta ', 'and be more productive', 'chatgpt.com_0',
    'current_node_id', '"model":', '"is_do_not',
]
_JSON_RE = re.compile(r'\{["\w]+:')
_HTML_RE = re.compile(r'<[a-zA-Z][^>]{0,30}>')

def is_real(s: str) -> bool:
    if not s or len(s.strip()) < 15:
        return False
    for n in _NOISE:
        if n in s:
            return False
    if _JSON_RE.search(s[:80]) or _HTML_RE.search(s[:120]):
        return False
    if s.strip().startswith('<'):
        return False
    alpha = sum(c.isalpha() for c in s)
    return alpha >= len(s) * 0.28

def ts_ist(ts: float) -> str:
    if not ts or ts < 1e9:
        return "Unknown"
    return datetime.fromtimestamp(ts + IST, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S IST')

# ── Load sources ──────────────────────────────────────────────────────────────
print(f'Loading old pipeline …')
old_raw = json.load(open(OLD, encoding='utf-8'))
old_items = old_raw if isinstance(old_raw, list) else old_raw.get('items', [])
print(f'  {len(old_items)} items')

# We'll also read the NEW file only if it doesn't contain old output
# (avoid recursion with previous runs of this script)
cur_raw = json.load(open(NEW, encoding='utf-8')) if os.path.isfile(NEW) else {}
cur_items = cur_raw.get('items', [])
cur_is_old_format = any('messages' in x for x in cur_items[:3])

# ── Build conversation map: CID → {title, update_time, is_archived, is_starred, msgs[]} ──
SKIP_TITLES = {
    'Unknown (deleted/orphaned conversation)', 'New chat', 'Student',
    'What is 5', 'What is apple', 'Test message response',
    'Testing cache behavior', 'Deleted Fragment Recovery', '',
}

convs: dict = {}   # cid → conv dict

def upsert(cid: str, title: str, ts: float,
           is_arch: bool, is_star: bool, messages: list):
    key = cid if cid else title[:40]
    if not key:
        return
    prev = convs.get(key)
    if prev is None:
        convs[key] = {
            'cid': cid, 'title': title, 'ts': ts,
            'is_archived': is_arch, 'is_starred': is_star,
            'msgs': list(messages),
        }
        return
    # Use highest ts only if it's from a trusted source (not batch ts)
    if ts > float(prev['ts'] or 0) and ts < 1_773_901_000:  # exclude batch ts
        prev['ts'] = ts
    if title and title not in SKIP_TITLES:
        prev['title'] = title
    prev['is_archived'] = is_arch or prev['is_archived']
    prev['is_starred']  = is_star or prev['is_starred']
    seen = {md5(m['snippet'][:80].encode()).hexdigest() for m in prev['msgs']}
    for m in messages:
        h = md5(m['snippet'][:80].encode()).hexdigest()
        if h not in seen:
            prev['msgs'].append(m)
            seen.add(h)

# ── Process OLD pipeline ──────────────────────────────────────────────────────
for item in old_items:
    cid   = (item.get('conversation_id') or '').strip()
    title = (item.get('title') or '').strip()
    if title in SKIP_TITLES:
        continue
    ts      = float(item.get('latest_update') or item.get('update_time') or 0)
    is_arch = bool(item.get('is_archived'))
    is_star = bool(item.get('is_starred'))

    msgs = []
    for m in (item.get('messages') or []):
        snip = (m.get('snippet') or m.get('text') or '').strip()
        if not is_real(snip):
            continue
        mid  = (m.get('message_id') or m.get('id') or '').strip()
        role = (m.get('role') or 'unknown').lower()
        mts  = float(m.get('timestamp') or m.get('update_time') or ts)
        msgs.append({'mid': mid, 'role': role, 'snippet': snip[:4000], 'ts': mts})

    upsert(cid, title, ts, is_arch, is_star, msgs)

print(f'After old pipeline: {len(convs)} unique conversations')

# ── Apply accurate timestamps from Live LS conversation-history scan ──────────
# Import here to avoid circular issues
try:
    sys.path.insert(0, BASE)
    import chatgpt_extractor as cex
    paths = cex.discover_paths()
    ls_dir = paths.get('ls', '')
    if ls_dir:
        ch = cex._scan_ls_conversation_history(ls_dir)
        print(f'LS conversation-history: {len(ch)} entries')
        for entry in ch:
            ecid  = entry.get('conversation_id', '')
            etitle= entry.get('title', '')
            ets   = float(entry.get('update_time') or 0)
            key   = ecid if ecid else etitle[:40]
            if key in convs and ets > 1e9:
                convs[key]['ts'] = ets          # overwrite with accurate ISO ts
                if etitle:
                    convs[key]['title'] = etitle
except Exception as e:
    print(f'  [warn] LS scan skipped: {e}')

# ── Sort conversations newest → oldest ────────────────────────────────────────
clist = sorted(convs.values(), key=lambda c: float(c['ts'] or 0), reverse=True)

# ── Build output in Claude schema: one entry per message ─────────────────────
out_items = []
for conv in clist:
    cid   = conv['cid']
    title = conv['title']
    ts    = float(conv['ts'] or 0)
    msgs  = sorted(conv['msgs'], key=lambda m: float(m['ts'] or 0))

    if not msgs:
        # Metadata-only — emit ONE placeholder entry (no snippet pollution)
        out_items.append({
            "conversation_id": cid,
            "current_node_id": "",
            "title": title,
            "model": "",
            "is_archived": conv['is_archived'],
            "is_starred":  conv['is_starred'],
            "update_time": ts,
            "payload": {
                "kind": "message",
                "message_id": "",
                "snippet": "[No content recovered — metadata only]",
                "role": ""
            }
        })
        continue

    for m in msgs:
        out_items.append({
            "conversation_id": cid,
            "current_node_id": m['mid'],
            "title": title,
            "model": "",
            "is_archived": conv['is_archived'],
            "is_starred":  conv['is_starred'],
            "update_time": ts,
            "payload": {
                "kind": "message",
                "message_id": m['mid'],
                "snippet": m['snippet'],
                "role": m['role']
            }
        })

# ── Write ─────────────────────────────────────────────────────────────────────
now_ist = ts_ist(datetime.utcnow().timestamp())
output = {
    "_forensic_notes": (
        "DIGITAL FORENSIC INTEGRITY STATEMENT: Contains ONLY data physically "
        "recovered from binary artifacts. Schema matches RECOVERED_CLAUDE_HISTORY.json."
    ),
    "total_conversations": len(clist),
    "total_messages": len(out_items),
    "extraction_time_ist": now_ist,
    "items": out_items
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

# Markdown
MD = os.path.join(BASE, 'reports', 'chatgpt', 'chatgpt_report.md')
lines = [f'# ChatGPT Forensic Report\n\n**Generated:** {now_ist}\n',
         f'**Total conversations:** {len(clist)}  |  **Total messages:** {len(out_items)}\n\n---\n']

for conv in clist:
    ts = float(conv['ts'] or 0)
    lines.append(f'\n## {conv["title"]}\n')
    lines.append(f'**Last updated (IST):** {ts_ist(ts)}  \n')
    lines.append(f'**Conversation ID:** `{conv["cid"]}`\n\n')
    msgs = sorted(conv['msgs'], key=lambda m: float(m['ts'] or 0))
    if not msgs:
        lines.append('*[No message content recovered — metadata only]*\n')
    else:
        for m in msgs:
            role = m['role'].upper()
            mt   = ts_ist(float(m['ts'] or 0))
            lines.append(f'**[{mt}] {role}:**\n\n{m["snippet"]}\n\n')
    lines.append('---\n')

with open(MD, 'w', encoding='utf-8') as f:
    f.writelines(lines)

# Summary
convs_with_msgs = sum(1 for c in clist if c['msgs'])
print(f'\n✓  Done')
print(f'   Conversations : {len(clist)}')
print(f'   With messages : {convs_with_msgs}')
print(f'   Metadata-only : {len(clist) - convs_with_msgs}')
print(f'   Total items   : {len(out_items)}')
print(f'   JSON  → {OUT}')
print(f'   MD    → {MD}')
print()
print('Newest 15 (with content):')
shown = 0
for item in out_items:
    if item['payload']['snippet'].startswith('[No content'):
        continue
    t   = item.get('update_time', 0)
    ts  = ts_ist(t)[:10]
    role = item['payload']['role'].upper()
    snip = item['payload']['snippet'][:70]
    print(f'  {ts} | {role:9s} | {item["title"]} | {snip}')
    shown += 1
    if shown >= 15:
        break

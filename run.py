"""
run.py  — LLM Artifact Forensic Tool (Unified)
═══════════════════════════════════════════════════════════════════════
All logic in one file. Run:
    python run.py

Steps performed:
  1. App selection menu (ChatGPT / Claude)
  2. Directory scanning & path detection
  3. Data extraction + merge with historical recovered data
  4. Single report output in reports/ root
     • reports/CHATGPT_FORENSIC_REPORT.json
     • reports/CHATGPT_FORENSIC_REPORT.md
      — or —
     • reports/CLAUDE_FORENSIC_REPORT.json
     • reports/CLAUDE_FORENSIC_REPORT.md
"""

import sys, io, os, re, json, glob, struct, shutil, hashlib, gzip
from datetime import datetime, timezone
from pathlib import Path

BASE    = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(BASE, "reports")
os.makedirs(REPORTS, exist_ok=True)

LOCAL   = os.getenv("LOCALAPPDATA", "")
APPDATA = os.getenv("APPDATA", "")
IST     = 5.5 * 3600   # seconds offset for IST


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ts_ist(ts: float) -> str:
    if not ts or ts < 1e9:
        return "Unknown"
    return datetime.fromtimestamp(ts + IST, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S IST")

def _safe_read(path: str) -> bytes:
    try:
        tmp = path + f"._r{os.getpid()}"
        shutil.copy2(path, tmp)
        with open(tmp, "rb") as f:
            data = f.read()
        os.remove(tmp)
        return data
    except Exception:
        return b""

def _snappy_sliding(raw: bytes):
    try:
        import cramjam
        CHUNK = 65536
        out = []
        for i in range(0, min(len(raw), 4*1024*1024), CHUNK//4):
            try:
                d = bytes(cramjam.snappy.decompress(raw[i:i+CHUNK]))
                if len(d) > 64:
                    out.append(d)
            except Exception:
                pass
        return out
    except ImportError:
        return []

def _sep(c="─", w=62):
    print(c * w)

def _header(title: str):
    _sep("═")
    print(f"  {title}")
    _sep("═")

# ═══════════════════════════════════════════════════════════════════════════════
# SNIPPET QUALITY GATE (shared by both pipelines)
# ═══════════════════════════════════════════════════════════════════════════════

_NOISE = [
    "[No cached content]", '{"conversation_id"', "}},",
    '"title":', '"is_archived"', '"mapping"', "current_node_id",
    "accountUserId", 'id"$', "client-created-root",
    '"kind":"message"', '"snippet":', "created=20", "updated=20",
    "og:url", "og:title", "<meta ", "and be more productive",
    "chatgpt.com_0", '"model":', '"is_do_not', "webRTC",
    "CERTIFICATE", "-----BEGIN",
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
    if s.strip().startswith("<"):
        return False
    alpha = sum(c.isalpha() for c in s)
    return alpha >= len(s) * 0.28


# ═══════════════════════════════════════════════════════════════════════════════
# PATH DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════════

def discover_chatgpt_paths() -> dict:
    """Find ChatGPT Desktop app data directories."""
    pat = os.path.join(LOCAL, "Packages", "OpenAI.ChatGPT-Desktop_*",
                       "LocalCache", "Roaming", "ChatGPT")
    roots = glob.glob(pat)
    if not roots:
        return {}
    root = roots[0]
    idb  = os.path.join(root, "IndexedDB")
    return {
        "app_root": root,
        "idb_ldb":  os.path.join(idb, "https_chatgpt.com_0.indexeddb.leveldb"),
        "idb_blob": os.path.join(idb, "https_chatgpt.com_0.indexeddb.blob"),
        "ls_ldb":   os.path.join(root, "Local Storage", "leveldb"),
        "cache":    os.path.join(root, "Cache", "Cache_Data"),
    }

def discover_claude_paths() -> dict:
    """Find Claude Desktop app data directories."""
    candidates = [
        os.path.join(LOCAL, "Packages", "AnthropicPBC.ClaudeAI_*",
                     "LocalCache", "Roaming", "Claude"),
        os.path.join(APPDATA, "Claude"),
        os.path.join(LOCAL,   "Claude"),
    ]
    for cand in candidates:
        roots = glob.glob(cand) if "*" in cand else ([cand] if os.path.isdir(cand) else [])
        if roots:
            root = roots[0]
            return {
                "app_root": root,
                "cache":    os.path.join(root, "Cache", "Cache_Data"),
                "ls_ldb":   os.path.join(root, "Local Storage", "leveldb"),
                "idb_ldb":  os.path.join(root, "IndexedDB"),
            }
    return {}

def _scan_dirs(paths: dict) -> list:
    """Print detected directories and return list of found ones."""
    found = []
    for label, path in paths.items():
        if label == "app_root":
            continue
        exists = os.path.isdir(path)
        status = "✓ FOUND" if exists else "✗ missing"
        fc     = ""
        if exists:
            files = glob.glob(os.path.join(path, "**", "*"), recursive=True)
            fc    = f"  ({len(files)} files)"
        print(f"    [{status}] {label}: {path}{fc}")
        if exists:
            found.append(path)
    return found


# ═══════════════════════════════════════════════════════════════════════════════
# CHATGPT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _ls_conversation_history(ls_dir: str) -> list:
    """Parse 'conversation-history' JSON from Local Storage LDB/LOG files."""
    results = []
    all_files = (
        sorted(glob.glob(os.path.join(ls_dir, "*.log")), key=os.path.getmtime, reverse=True) +
        sorted(glob.glob(os.path.join(ls_dir, "*.ldb")), key=os.path.getmtime, reverse=True)
    )
    pat = re.compile(r'conversation-history[^\{]{0,40}(\{"value":\{"pages":\[)')
    for fpath in all_files:
        raw = _safe_read(fpath)
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        for m in pat.finditer(text):
            start = m.start(1)
            depth, end = 0, start
            for i in range(start, min(start + 800_000, len(text))):
                c = text[i]
                if c == "{":   depth += 1
                elif c == "}": depth -= 1
                if depth == 0: end = i + 1; break
            if end <= start:
                continue
            try:
                payload = json.loads(text[start:end])
            except Exception:
                continue
            pages = (payload.get("value") or payload).get("pages", [])
            for page in pages:
                for item in (page.get("items") or []):
                    if not isinstance(item, dict):
                        continue
                    cid   = (item.get("id") or "").strip()
                    title = (item.get("title") or "").strip()
                    ts    = 0.0
                    for ts_str in (item.get("update_time",""), item.get("create_time","")):
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(
                                    ts_str.replace("Z","+00:00")).timestamp()
                                break
                            except Exception:
                                pass
                    results.append({
                        "conversation_id": cid,
                        "title": title,
                        "update_time": ts,
                        "is_archived": bool(item.get("is_archived")),
                        "is_starred":  bool(item.get("is_starred")),
                    })
    # Deduplicate
    seen: dict = {}
    for r in results:
        cid = r["conversation_id"]
        if cid not in seen or r["update_time"] > seen[cid]["update_time"]:
            seen[cid] = r
    return list(seen.values())


def run_chatgpt(paths: dict):
    """Full ChatGPT extraction pipeline → single report."""
    _sep("─")
    print("  [1/4] Reading historical recovered data …")
    old_file = os.path.join(REPORTS, "RECOVERED_CHATGPT_GROUPED.json")
    if not os.path.isfile(old_file):
        print(f"  [!] {old_file} not found — live-only mode")
        old_items = []
    else:
        old_raw   = json.load(open(old_file, encoding="utf-8"))
        old_items = old_raw if isinstance(old_raw, list) else old_raw.get("items", [])
        print(f"      → {len(old_items)} historical records loaded")

    SKIP = {"Unknown (deleted/orphaned conversation)","New chat","Student",
            "What is 5","What is apple","Test message response",
            "Testing cache behavior","Deleted Fragment Recovery",""}

    convs: dict = {}   # key → {cid, title, ts, msgs, is_archived, is_starred}

    def upsert(cid, title, ts, is_arch, is_star, msgs):
        key = cid if cid else title[:40]
        if not key:
            return
        prev = convs.get(key)
        if prev is None:
            convs[key] = {"cid":cid,"title":title,"ts":ts,
                          "is_archived":is_arch,"is_starred":is_star,
                          "msgs":list(msgs)}
            return
        if cid and not prev["cid"]:
            prev["cid"] = cid
        if title and title not in SKIP:
            prev["title"] = title
        # Keep highest ts (only accept batch-free ones ≤ 1773901000)
        if ts > float(prev["ts"] or 0) and ts < 1_773_901_000:
            prev["ts"] = ts
        prev["is_archived"] = is_arch or prev["is_archived"]
        prev["is_starred"]  = is_star or prev["is_starred"]
        seen = {m["snippet"][:100] for m in prev["msgs"]}
        for m in msgs:
            if m["snippet"][:100] not in seen:
                prev["msgs"].append(m)
                seen.add(m["snippet"][:100])

    # ── Seed from old pipeline ────────────────────────────────────────────
    for item in old_items:
        cid   = (item.get("conversation_id") or "").strip()
        title = (item.get("title") or "").strip()
        if title in SKIP:
            continue
        ts    = float(item.get("latest_update") or item.get("update_time") or 0)
        msgs  = []
        for m in (item.get("messages") or []):
            snip = (m.get("snippet") or m.get("text") or "").strip()
            if is_real(snip):
                msgs.append({"mid":(m.get("message_id") or m.get("id") or ""),
                              "role":(m.get("role") or "unknown").lower(),
                              "snippet":snip[:4000],
                              "ts":float(m.get("timestamp") or m.get("update_time") or ts)})
        upsert(cid, title, ts, bool(item.get("is_archived")), bool(item.get("is_starred")), msgs)

    print(f"      → {len(convs)} unique conversations after deduplication")

    # ── Apply accurate per-conversation timestamps from Live LS ──────────
    print("  [2/4] Scanning live Local Storage for accurate timestamps …")
    ls_dir = paths.get("ls_ldb","")
    if os.path.isdir(ls_dir):
        ch = _ls_conversation_history(ls_dir)
        applied = 0
        for entry in ch:
            ecid  = entry.get("conversation_id","")
            etitle= entry.get("title","")
            ets   = float(entry.get("update_time") or 0)
            key   = ecid if ecid else etitle[:40]
            if key in convs and ets > 1e9:
                convs[key]["ts"] = ets
                if etitle:
                    convs[key]["title"] = etitle
                applied += 1
        print(f"      → {len(ch)} entries found, {applied} timestamps updated")
    else:
        print("      → Local Storage not found")

    # ── Attempt live cache extraction ─────────────────────────────────────
    print("  [3/4] Scanning live HTTP cache …")
    cache_dir = paths.get("cache","")
    cache_found = 0
    if os.path.isdir(cache_dir):
        try:
            import chatgpt_extractor as cex
            cache_hits = cex.scan_cache(cache_dir, verbose=False)
            for h in cache_hits:
                cid   = h.get("conversation_id","")
                title = h.get("title","")
                ts    = float(h.get("update_time") or 0)
                msgs  = []
                for m in h.get("messages",[]):
                    snip = m.get("snippet","")
                    if is_real(snip):
                        msgs.append({"mid":m.get("message_id",""),
                                     "role":m.get("role","unknown"),
                                     "snippet":snip[:4000],
                                     "ts":float(m.get("timestamp") or ts)})
                upsert(cid, title, ts, False, False, msgs)
                cache_found += 1
        except Exception as e:
            print(f"      [warn] Cache scan error: {e}")
        print(f"      → {cache_found} conversations from live cache")
    else:
        print("      → Cache directory not found")

    # ── Build output ──────────────────────────────────────────────────────
    print("  [4/4] Building report …")
    clist = sorted(convs.values(), key=lambda c: float(c["ts"] or 0), reverse=True)

    out_items = []
    for conv in clist:
        cid   = conv["cid"]
        title = conv["title"]
        ts    = float(conv["ts"] or 0)
        msgs  = sorted(conv["msgs"], key=lambda m: m.get("ts",0))
        if not msgs:
            out_items.append({
                "conversation_id": cid,
                "current_node_id": "",
                "title": title,
                "model": "",
                "is_archived": conv["is_archived"],
                "is_starred":  conv["is_starred"],
                "update_time": ts,
                "payload": {"kind":"message","message_id":"",
                            "snippet":"[No content recovered — metadata only]",
                            "role":""}
            })
        else:
            for m in msgs:
                out_items.append({
                    "conversation_id": cid,
                    "current_node_id": m["mid"],
                    "title": title,
                    "model": "",
                    "is_archived": conv["is_archived"],
                    "is_starred":  conv["is_starred"],
                    "update_time": ts,
                    "payload": {"kind":"message","message_id":m["mid"],
                                "snippet":m["snippet"],"role":m["role"]}
                })

    _write_report("CHATGPT", clist, out_items)


# ═══════════════════════════════════════════════════════════════════════════════
# CLAUDE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def run_claude(paths: dict):
    """Full Claude extraction pipeline → single report."""
    _sep("─")

    # ── Try live cache first via claude_extractor ─────────────────────────
    print("  [1/3] Attempting live cache extraction …")
    live_items = []
    try:
        import claude_extractor
        live_convs = claude_extractor.run(verbose=False)
        for h in live_convs:
            for m in h.get("messages", []):
                snip = m.get("snippet","").strip()
                if not is_real(snip):
                    continue
                live_items.append({
                    "conversation_id": h.get("conversation_id",""),
                    "current_node_id": m.get("message_id",""),
                    "title": h.get("title",""),
                    "model": h.get("model",""),
                    "is_archived": False,
                    "is_starred":  False,
                    "update_time": float(h.get("update_time") or 0),
                    "payload": {
                        "kind": "message",
                        "message_id": m.get("message_id",""),
                        "snippet": snip[:4000],
                        "role": m.get("role","unknown")
                    }
                })
        print(f"      → {len(live_items)} live messages found")
    except Exception as e:
        print(f"      → Live extraction failed: {e}")

    # ── Use RECOVERED_CLAUDE_HISTORY.json as primary source ───────────────
    print("  [2/3] Loading previously recovered Claude history …")
    rec_file = os.path.join(REPORTS, "RECOVERED_CLAUDE_HISTORY.json")
    rec_items = []
    if os.path.isfile(rec_file):
        rec_raw  = json.load(open(rec_file, encoding="utf-8"))
        rec_items = rec_raw.get("items", [])
        print(f"      → {len(rec_items)} items in RECOVERED_CLAUDE_HISTORY.json")
    else:
        print(f"      → {rec_file} not found")

    # ── Merge all items — real content AND metadata-only ─────────────────
    print("  [3/3] Merging & deduplicating …")

    _TS_PAT = re.compile(r'(?:updated|created)=(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)')

    def _parse_iso_from_snippet(snip: str) -> float:
        """Extract timestamp from '[No cached content] updated=...' strings."""
        for m in _TS_PAT.finditer(snip):
            try:
                return datetime.fromisoformat(
                    m.group(1).replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        return 0.0

    def _clean_item(item: dict) -> dict:
        """Return a schema-clean copy — remove source_file, fix timestamps."""
        snip = (item.get("payload", {}).get("snippet") or "").strip()
        ts   = float(item.get("update_time") or 0)

        # For meta-only: parse better ts from snippet if main ts looks wrong
        is_meta = snip.startswith("[No cached content]") or not is_real(snip)
        if is_meta:
            parsed_ts = _parse_iso_from_snippet(snip)
            if parsed_ts > 1e9:
                ts = parsed_ts
            snip = "[No content recovered — metadata only]"

        return {
            "conversation_id": (item.get("conversation_id") or "").strip(),
            "current_node_id": (item.get("current_node_id") or "").strip(),
            "title":           (item.get("title") or "").strip(),
            "model":           (item.get("model") or ""),
            "is_archived":     bool(item.get("is_archived")),
            "is_starred":      bool(item.get("is_starred")),
            "update_time":     ts,
            "payload": {
                "kind":       item.get("payload", {}).get("kind", "message"),
                "message_id": (item.get("payload", {}).get("message_id") or "").strip(),
                "snippet":    snip[:4000],
                "role":       (item.get("payload", {}).get("role") or "").strip(),
            },
        }

    seen_keys: set = set()
    out_items: list = []

    def add_item(item: dict):
        clean = _clean_item(item)
        cid  = clean["conversation_id"]
        mid  = clean["current_node_id"] or clean["payload"]["message_id"]
        snip = clean["payload"]["snippet"]
        # Dedup key: (cid, mid) or (cid, snippet_hash) for meta-only
        if mid:
            key = f"{cid}::{mid}"
        else:
            key = f"{cid}::{hashlib.md5(snip[:80].encode()).hexdigest()}"
        if key not in seen_keys:
            seen_keys.add(key)
            out_items.append(clean)

    # RECOVERED_CLAUDE_HISTORY first (richer — all 23 entries including meta)
    for item in rec_items:
        add_item(item)
    # Live cache on top
    for item in live_items:
        add_item(item)

    # Sort newest → oldest
    out_items.sort(key=lambda x: float(x.get("update_time", 0)), reverse=True)

    cid_set = {x["conversation_id"] for x in out_items}
    total_real = sum(1 for x in out_items
                     if not x["payload"]["snippet"].startswith("[No content"))

    print(f"      → {len(out_items)} total items ({total_real} with real content, "
          f"{len(out_items)-total_real} metadata-only)")

    _write_report("CLAUDE", list(cid_set), out_items, is_claude=True)



# ═══════════════════════════════════════════════════════════════════════════════
# REPORT WRITER (single-file output)
# ═══════════════════════════════════════════════════════════════════════════════

def _write_report(app: str, clist, out_items: list, is_claude: bool = False):
    now = ts_ist(datetime.utcnow().timestamp())
    total_convs = len(clist)
    total_msgs  = len(out_items)
    with_content = sum(1 for x in out_items
                       if not x["payload"]["snippet"].startswith("[No content"))

    json_path = os.path.join(REPORTS, f"{app}_FORENSIC_REPORT.json")
    md_path   = os.path.join(REPORTS, f"{app}_FORENSIC_REPORT.md")

    # ── JSON ──────────────────────────────────────────────────────────────
    output = {
        "_forensic_notes": (
            "DIGITAL FORENSIC INTEGRITY STATEMENT: Contains ONLY data physically "
            "recovered from binary artifacts. Schema matches RECOVERED_CLAUDE_HISTORY.json."
        ),
        "app": app,
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "messages_with_content": with_content,
        "extraction_time_ist": now,
        "items": out_items,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── Markdown ──────────────────────────────────────────────────────────
    # Group items by conversation_id for readable report
    by_conv: dict = {}
    for item in out_items:
        cid = item["conversation_id"]
        by_conv.setdefault(cid, []).append(item)

    lines = [
        f"# {app} Forensic Extraction Report\n\n",
        f"**Generated:** {now}  \n",
        f"**App:** {app}  \n",
        f"**Conversations:** {total_convs}  \n",
        f"**Messages with content:** {with_content}  \n\n",
        "---\n\n",
    ]

    # Sort conversations by newest message
    def conv_ts(items_list):
        return max((float(x.get("update_time",0)) for x in items_list), default=0)

    for cid, citems in sorted(by_conv.items(), key=lambda kv: conv_ts(kv[1]), reverse=True):
        title = citems[0].get("title","(untitled)")
        ts    = conv_ts(citems)
        lines.append(f"\n## {title}\n\n")
        lines.append(f"**Last updated (IST):** {ts_ist(ts)}  \n")
        lines.append(f"**Conversation ID:** `{cid}`\n\n")
        msgs_sorted = sorted(citems, key=lambda x: float(x.get("update_time",0)))
        has_real = any(not x["payload"]["snippet"].startswith("[No content") for x in msgs_sorted)
        if not has_real:
            lines.append("*[No message content recovered — metadata only]*\n")
        else:
            for item in msgs_sorted:
                snip = item["payload"]["snippet"]
                if snip.startswith("[No content"):
                    continue
                role = (item["payload"].get("role") or "unknown").upper()
                mt   = ts_ist(float(item.get("update_time",0)))
                lines.append(f"**[{mt}] {role}:**\n\n{snip}\n\n")
        lines.append("---\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    _sep()
    print(f"\n  ✓ DONE — {app}")
    print(f"    Conversations  : {total_convs}")
    print(f"    Messages found : {with_content}")
    print(f"\n    JSON → {json_path}")
    print(f"    MD   → {md_path}")
    _sep()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = r"""
╔══════════════════════════════════════════════════════════════════╗
║          LLM Artifact Forensic Tool  v3.0                        ║
║          Digital Evidence Recovery — ChatGPT & Claude            ║
╚══════════════════════════════════════════════════════════════════╝
"""

MENU = """
  Select Application:
  ─────────────────────────────────────────
    1.  ChatGPT    (LevelDB + Cache + Historical)
    2.  Claude     (Cache + RECOVERED_CLAUDE_HISTORY)
    0.  Exit
  ─────────────────────────────────────────
  Enter choice [0/1/2]: """


def main():
    # UTF-8 output for Windows terminal
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    print(BANNER)

    while True:
        try:
            choice = input(MENU).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Exiting.")
            break

        if choice not in ("0","1","2"):
            print("  Invalid choice.")
            continue

        if choice == "0":
            print("\n  Exiting.")
            break

        app = "ChatGPT" if choice == "1" else "Claude"
        _header(f"{app} Forensic Extraction")

        # ── Path detection ──────────────────────────────────────────────
        print(f"\n  Scanning for {app} directories …")
        paths = discover_chatgpt_paths() if choice == "1" else discover_claude_paths()

        if not paths:
            print(f"\n  [!] {app} Desktop installation not detected.")
            print(f"      (For ChatGPT: install from Microsoft Store)")
            print(f"      (For Claude:  install from anthropic.com)")
            if choice == "2":
                print(f"\n  Proceeding with RECOVERED_CLAUDE_HISTORY.json only …")
                paths = {}
            else:
                input("\n  Press Enter to return to menu …")
                continue

        _scan_dirs(paths)
        print()

        # ── Run pipeline ────────────────────────────────────────────────
        import time
        t0 = time.time()
        if choice == "1":
            run_chatgpt(paths)
        else:
            run_claude(paths)
        print(f"\n  Completed in {time.time()-t0:.1f}s")

        try:
            again = input("\n  Run another? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if again != "y":
            print("  Exiting.")
            break


if __name__ == "__main__":
    main()

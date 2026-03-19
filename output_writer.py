"""
output_writer.py  –  Shared JSON + Markdown writer for ChatGPT and Claude.

call:
    from output_writer import write_outputs
    write_outputs("chatgpt", conversations)
    write_outputs("claude", conversations)

conversations is a list of dicts:
{
    "conversation_id": str,
    "title":           str,
    "update_time":     float,       # Unix seconds
    "messages": [
        {
            "message_id": str,
            "role":       str,      # "user" | "assistant" | "system"
            "snippet":    str,
            "timestamp":  float,    # Unix seconds
        }
    ]
}
"""
import os
import json
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
IST_OFFSET = 5.5 * 3600   # UTC+05:30

ROLE_EMOJI = {
    "user":      "👤 USER",
    "assistant": "🤖 ASSISTANT",
    "system":    "⚙️  SYSTEM",
    "unknown":   "❓ UNKNOWN",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _to_ist(ts: float) -> str:
    if not ts or ts <= 0:
        return "Unknown time"
    try:
        return datetime.fromtimestamp(ts + IST_OFFSET, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )
    except Exception:
        return "Unknown time"


def _build_json_item(conv: dict) -> dict:
    """Convert internal conversation dict → output JSON schema."""
    msgs = conv.get("messages", [])
    # Pick best single payload (highest-ts message with real content)
    best = None
    for m in sorted(msgs, key=lambda x: x.get("timestamp", 0), reverse=True):
        if m.get("snippet") and not m["snippet"].startswith("[No cached"):
            best = m
            break
    if best is None and msgs:
        best = msgs[0]

    snippet = (best or {}).get("snippet", "")
    role    = (best or {}).get("role", "")
    msg_id  = (best or {}).get("message_id", "")
    ut      = conv.get("update_time", 0.0)

    if not snippet:
        iso = datetime.fromtimestamp(ut, tz=timezone.utc).strftime(
            "updated=%Y-%m-%dT%H:%M:%S.%fZ"
        ) if ut > 0 else ""
        snippet = f"[No cached content] {iso}".strip()

    return {
        "conversation_id": conv.get("conversation_id", ""),
        "title":           conv.get("title", ""),
        "update_time":     ut,
        "update_time_ist": _to_ist(ut),
        "payload": {
            "kind":       "message",
            "message_id": msg_id,
            "snippet":    snippet,
            "role":       role,
        },
    }


# ─── Main writer ──────────────────────────────────────────────────────────────
def write_outputs(app: str, conversations: list, quiet: bool = False) -> dict:
    """
    Write JSON + Markdown for `app` ("chatgpt" or "claude").
    Returns { "json_path": ..., "md_path": ..., "count": ... }.
    """
    out_dir = os.path.join(BASE, "reports", app)
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, f"{app}_history.json")
    md_path   = os.path.join(out_dir, f"{app}_report.md")

    # ── Sort conversations newest → oldest ────────────────────────────────────
    conversations = sorted(
        conversations,
        key=lambda c: float(c.get("update_time") or 0),
        reverse=True,
    )

    # ── JSON ──────────────────────────────────────────────────────────────────
    json_items  = [_build_json_item(c) for c in conversations]
    json_output = {
        "_forensic_notes": (
            "DIGITAL FORENSIC INTEGRITY STATEMENT: Data physically recovered from "
            f"binary artifacts. No AI-synthesised content. App: {app.upper()}."
        ),
        "total_conversations": len(json_items),
        "items": json_items,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=2, ensure_ascii=False)

    # ── Markdown ──────────────────────────────────────────────────────────────
    lines = []
    lines.append(f"# {app.upper()} Recovered Conversations — Forensic Report")
    lines.append("")
    lines.append(f"**Generated:** {_to_ist(0).replace('Unknown time', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))}")
    lines.append(f"**Total conversations:** {len(conversations)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not conversations:
        lines.append("## No recoverable conversation data found")
        lines.append("")
        lines.append(
            "The forensic scan could not locate any readable conversation artifacts "
            "for this application."
        )
    else:
        for conv in conversations:
            title    = conv.get("title") or "(untitled)"
            cid      = conv.get("conversation_id", "")
            ut       = float(conv.get("update_time") or 0)
            messages = conv.get("messages", [])
            is_del   = conv.get("is_deleted", False)

            del_tag = " `[DELETED]`" if is_del else ""
            lines.append(f"## Conversation: {title}{del_tag}")
            lines.append("")
            lines.append(f"**ID:** `{cid}`  ")
            lines.append(f"**Last updated:** {_to_ist(ut)}")
            lines.append(f"**Messages:** {len(messages)}")
            lines.append("")

            if messages:
                for msg in sorted(messages, key=lambda m: m.get("timestamp", 0)):
                    role    = msg.get("role", "unknown")
                    snippet = msg.get("snippet", "")
                    ts      = float(msg.get("timestamp") or ut)
                    label   = ROLE_EMOJI.get(role, f"❓ {role.upper()}")
                    lines.append(f"**[{_to_ist(ts)}] {label}:**")
                    lines.append(snippet)
                    lines.append("")
            else:
                payload = conv.get("payload", {})
                snip = payload.get("snippet", "")
                if snip:
                    role  = payload.get("role", "unknown")
                    label = ROLE_EMOJI.get(role, f"❓ {role.upper()}")
                    lines.append(f"**[{_to_ist(ut)}] {label}:**")
                    lines.append(snip)
                    lines.append("")
                else:
                    lines.append("*No message content recovered.*")
                    lines.append("")

            lines.append("---")
            lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    result = {"json_path": json_path, "md_path": md_path, "count": len(conversations)}
    if not quiet:
        print(f"  [✓] JSON  → {json_path}")
        print(f"  [✓] MD    → {md_path}")
        print(f"  [✓] Total → {len(conversations)} conversations")

    return result

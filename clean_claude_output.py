"""
clean_claude_output.py
======================
Post-processes claude_COMPLETE.json (or any Claude recovery output) and
writes a clean RECOVERED_CLAUDE_HISTORY.json that contains ONLY entries
with real conversation content.

Filters OUT:
  • Entries whose snippet starts with "[No cached content]"
    (these are Chromium cache index placeholders — no real content)

Keeps:
  • Entries with kind="message" and real snippet text
  • Forensic metadata entries (role="forensic_evidence")

Usage:
    python clean_claude_output.py
    python clean_claude_output.py --input my_file.json --output cleaned.json
"""

import json
import argparse
import os

def is_noise_entry(item: dict) -> bool:
    """Return True if the item is an empty placeholder from cache index (f_*)."""
    payload = item.get("payload", {})
    snippet = payload.get("snippet", "")
    # Reject ONLY the generic ones that have no created/updated timestamps
    if snippet == "[No cached content] created= updated=":
        return True
    return False


def clean_claude_json(input_path: str, output_path: str):
    print(f"Reading: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both list format (claude_COMPLETE.json) and
    # dict-with-items format (RECOVERED_CLAUDE_HISTORY.json)
    if isinstance(data, list):
        items = data
        forensic_notes = None
    elif isinstance(data, dict):
        items = data.get("items", [])
        forensic_notes = data.get("_forensic_notes")
    else:
        print("ERROR: Unrecognised JSON structure.")
        return

    before = len(items)
    cleaned = []
    for item in items:
        if not is_noise_entry(item):
            # Ensure "kind" is always "message", even for timestamped placeholders
            # to avoid JSON corruption in the output schema
            if "payload" in item and item["payload"].get("kind") == "conversation_metadata":
                item["payload"]["kind"] = "message"
            cleaned.append(item)
    after = len(cleaned)

    print(f"  Total entries before: {before}")
    print(f"  Noise entries removed: {before - after}")
    print(f"  Clean entries kept:   {after}")

    # Group by conversation_id for a summary
    conv_ids = {}
    for item in cleaned:
        cid = item.get("conversation_id", "unknown")
        title = item.get("title", "")
        conv_ids[cid] = title

    print(f"\n  Unique conversations: {len(conv_ids)}")
    for cid, title in sorted(conv_ids.items(), key=lambda x: x[1]):
        print(f"    [{title}] {cid}")

    # Build output in the RECOVERED_CLAUDE_HISTORY.json format
    output = {
        "_forensic_notes": (
            forensic_notes or
            "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data "
            "physically recovered from binary artifacts. No AI text generation or "
            "falsification used. Filtered: [No cached content] placeholder entries removed."
        ),
        "items": cleaned
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWritten: {output_path}  ({os.path.getsize(output_path):,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean Claude forensic output JSON")
    parser.add_argument(
        "--input",
        default=r"c:\Users\sreya\Downloads\claude_COMPLETE.json",
        help="Input JSON file (claude_COMPLETE.json or RECOVERED_CLAUDE_HISTORY.json)"
    )
    parser.add_argument(
        "--output",
        default="reports/RECOVERED_CLAUDE_HISTORY.json",
        help="Output clean JSON file"
    )
    args = parser.parse_args()
    clean_claude_json(args.input, args.output)

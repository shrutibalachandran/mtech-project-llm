"""
forensic_utils.py
=================
Shared forensic utility helpers for the LLM Artifact Forensic Pipeline.

FORENSIC INTEGRITY NOTICE:
    This module enforces the strict no-hallucination rule that is fundamental
    to sound digital forensic analysis.  Every helper here operates only on
    data that *physically exists* in recovered binary evidence.

    is_hallucinated() detects and rejects any text that contains phrases
    commonly produced by AI summarisers, reconstituion engines, or generic
    UI strings — none of which represent real conversation content.
"""

import re
import json
import hashlib

# ---------------------------------------------------------------------------
# Section 1 — Hallucination Blocklist
# ---------------------------------------------------------------------------

# Phrases that are NEVER produced by a real user or assistant turn.
# They typically come from:
#   • AI-generated "reconstruction" summaries
#   • Chromium UI strings embedded in page bundles
#   • ChatGPT / Claude sidebar metadata labels
#   • Previous versions of this tool that incorrectly synthesised context
#
# If any of these phrases appear in a snippet, the fragment MUST be discarded
# because it does not represent authentic evidence from a conversation.

HALLUCINATION_PHRASES: list[str] = [
    "Search History",
    "Context:",
    "Highlights",
    "Reconstructed Timeline",
    "Metadata indicates",
    # Additional UI / AI-synthesis noise that has appeared in past runs
    "found in raw cache block",
    "Forensic Hit:",
    "Deleted Fragment Recovery",
    "Orphan Fragment:",
    "*Metadata indicates",
    "## 📂 Highlights",
    "Reconstructed from recovered",
]


def is_hallucinated(text: str) -> bool:
    """
    Return True if *text* contains any phrase from HALLUCINATION_PHRASES.

    Rationale for digital forensics:
        Including AI-generated reconstruction text in an evidence report
        pollutes the forensic record with fabricated content, which is
        inadmissible and misleading.  This function acts as the final
        quality gate before any artifact is written to disk.

    Args:
        text: The snippet text to inspect.

    Returns:
        True  → text is tainted; discard this artifact.
        False → text is clean; may be included in the report.
    """
    if not isinstance(text, str):
        return False
    for phrase in HALLUCINATION_PHRASES:
        if phrase in text:
            return True
    return False


# ---------------------------------------------------------------------------
# Section 2 — Binary Noise Cleaner
# ---------------------------------------------------------------------------

def clean_binary_noise(data: bytes) -> str:
    """
    Convert raw binary data to a readable string by:
      1. Decoding with UTF-8 (replacing undecodable bytes with a placeholder).
      2. Stripping non-printable / non-ASCII control characters (except
         whitespace characters \\t, \\n, \\r which are preserved as a space).
      3. Collapsing repeated whitespace into a single space.
      4. Stripping leading/trailing whitespace.

    This function does NOT interpret, summarise, or rewrite the content.
    It only removes binary debris that is structurally meaningless.

    Args:
        data: Raw bytes from a binary artifact.

    Returns:
        A cleaned, printable string derived solely from the input bytes.
    """
    if not isinstance(data, (bytes, bytearray)):
        return ""

    # Decode bytes — replace decode failures with the replacement character
    text = data.decode("utf-8", errors="replace")

    # Replace control characters (except printable whitespace) with a space
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]", " ", text)

    # Collapse multiple whitespace into single space
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Section 3 — .bin Fragment Gate
# ---------------------------------------------------------------------------

def should_save_bin(text: str) -> bool:
    """
    Decide whether a recovered text fragment is substantial enough to write
    to a .bin fragment file.

    Saves the fragment if EITHER condition is true:
      • len(text) > 40   — fragment has meaningful readable length
      • text is valid JSON — fragment contains a structured object

    This prevents the creation of thousands of zero-value micro-fragments
    (single words, single characters, or pure binary debris).

    Args:
        text: The cleaned string to evaluate.

    Returns:
        True  → fragment is worth saving.
        False → fragment is too small / meaningless.
    """
    if not text:
        return False

    # Condition 1: length threshold
    if len(text.strip()) > 60:
        return True

    # Condition 2: valid JSON object or array
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            return True
        except (json.JSONDecodeError, ValueError):
            pass

    return False


# ---------------------------------------------------------------------------
# Section 4 — General Helpers
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Return a normalised version of *text* for deduplication comparisons.
    Collapses all whitespace and lowercases.  Does not alter the content
    that gets stored — only used for hash comparison.
    """
    if not text:
        return ""
    return re.sub(r"\s+", "", text).lower()


def md5_hash(text: str) -> str:
    """Return MD5 hex digest of the first 1024 characters of normalised text."""
    norm = normalize_text(text)
    return hashlib.md5(norm[:1024].encode("utf-8", errors="replace")).hexdigest()


def extract_key_values_regex(raw_text: str) -> dict:
    """
    Fallback parser for malformed JSON.
    Extracts common LLM conversation fields via regex even when structural
    integrity of the JSON is lost.

    Only extracts data that is literally present in raw_text — does not
    synthesise or infer missing values.
    """
    patterns = {
        "title":           r'["\']title["\']\s*:\s*["\'](.*?)["\']',
        "content":         r'["\']content["\']\s*:\s*["\'](.*?)["\']',
        "text":            r'["\']text["\']\s*:\s*["\'](.*?)["\']',
        "conversation_id": r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
        "timestamp":       r'["\'](?:update_time|create_time|time)["\']\s*:\s*(\d{10}(?:\.\d+)?)',
    }
    results: dict = {}
    for key, pattern in patterns.items():
        matches = re.findall(pattern, raw_text, re.I)
        if matches:
            results[key] = matches[-1]
    return results


def calculate_entropy(text: str) -> float:
    """
    Simple heuristic to distinguish conversational text from base64 /
    system noise.  Conversational text has spaces and punctuation;
    encoded data does not.
    """
    if not text:
        return 0.0
    spaces = text.count(" ") / len(text)
    punctuation = sum(1 for c in text if c in ".,?!") / len(text)
    return (spaces * 2) + punctuation


def is_conversational(text: str, threshold: float = 0.05) -> bool:
    """Return True if *text* looks like human-readable prose."""
    return calculate_entropy(text) > threshold


def create_orphan_entry(raw_data: str, source_metadata: dict | None = None) -> dict:
    """
    Wraps a fragmented, malformed artifact in a standard forensic container.
    Only stores data extracted directly from raw_data — no invented content.
    """
    extracted = extract_key_values_regex(raw_data)
    snippet = extracted.get("text") or extracted.get("content") or raw_data[:500]

    return {
        "conversation_id": extracted.get("conversation_id", ""),
        "current_node_id": f"orphan_{hashlib.md5(raw_data.encode(errors='ignore')).hexdigest()[:8]}",
        "title": extracted.get("title", ""),
        "is_archived": False,
        "is_starred": None,
        "update_time": float(extracted.get("timestamp", 0)),
        "payload": {
            "kind": "message",
            "message_id": f"orphan_{hashlib.md5(raw_data.encode(errors='ignore')).hexdigest()[:8]}",
            "snippet": snippet,
        },
    }

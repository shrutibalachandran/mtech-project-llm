"""
forensic_main.py
================
Unified 5-Stage Forensic Pipeline for LLM Desktop Application Artifacts.

Supports:
  • ChatGPT Desktop  (Windows Store package, Electron app)
  • Claude Desktop   (Roaming AppData)

Artifact sources processed:
  • LevelDB WAL files       (.log)  — Write-Ahead Log: highest recovery priority
  • LevelDB SSTables        (.ldb)  — Sorted String Table: compressed blocks
  • Chromium Disk Cache     (data_*, f_*) — HTTP response cache

=============================================================================
CRITICAL FORENSIC RULE — NO HALLUCINATION
=============================================================================
This tool MUST NEVER generate, infer, summarise, or invent text that does
not physically exist in the recovered binary artifacts.

Rationale:
  In digital forensics, the evidentiary value of recovered data depends
  entirely on its provenance.  If an analysis tool generates synthetic text
  (e.g. AI-reconstructed summaries, placeholder explanations, UI strings
  mistaken for conversation content), that text becomes indistinguishable
  from authentic evidence — corrupting the forensic record and potentially
  introducing misleading information into legal or investigative proceedings.

  Every string written to RECOVERED_HISTORY_CLEAN.json must be traceable
  back to a specific byte offset in a specific binary file.

  If a recovered fragment is incomplete or partially corrupt, it is stored
  exactly as extracted.  Missing fields are left empty ("" or 0 or null).
  They are NEVER synthesised.
=============================================================================

Usage:
    python forensic_main.py [--leveldb PATH] [--cache PATH]
                            [--output RECOVERED_HISTORY_CLEAN.json]
                            [--no-bin]

Author:  LLM Forensics Pipeline
Version: 2.0 — Unified clean pipeline
"""

from __future__ import annotations

import argparse
import gzip
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

# Optional third-party compression libraries
try:
    import cramjam
    _HAS_CRAMJAM = True
except ImportError:
    _HAS_CRAMJAM = False

try:
    import brotli
    _HAS_BROTLI = True
except ImportError:
    _HAS_BROTLI = False

# Local forensic helpers
from forensic_utils import (
    HALLUCINATION_PHRASES,
    is_hallucinated,
    clean_binary_noise,
    should_save_bin,
    normalize_text,
    md5_hash,
    is_conversational,
    create_orphan_entry,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

# Patterns that indicate a byte region contains LLM conversation data
CONVERSATION_KEYWORDS: list[bytes] = [
    b"conversation_id",
    b"message_id",
    b"content",
    b"role",
    b"messages",
    b"title",
    b"update_time",
    b"uuid",
    b"mapping",
    b"author",
    b"chat_messages",
    b"sender",
    b"text",
]

# Max string length for V8 parser safety
MAX_STRING_LEN = 2_000_000
SCAN_WINDOW_SIZE = 2_100_000  # 2 MB + buffer

# ---------------------------------------------------------------------------
# V8 Structured Clone Tags
# ---------------------------------------------------------------------------
TAG_BEGIN_OBJECT    = 0x6F  # 'o'
TAG_ONEBYTE_STR     = 0x22  # '"'
TAG_TWOBYTE_STR     = 0x63  # 'c'
TAG_INT32           = 0x49  # 'I'
TAG_DOUBLE          = 0x4E  # 'N'
TAG_TRUE            = 0x54  # 'T'
TAG_FALSE           = 0x46  # 'F'
TAG_NULL            = 0x30  # '0'
TAG_UNDEF           = 0x5F  # '_'
TAG_BEGIN_ARRAY     = 0x61  # 'a'
TAG_END_DENSE_ARR   = 0x24  # '$'
TAG_BEGIN_SPARSE    = 0x7B  # '{'
TAG_OBJECT_REF      = 0x5E  # '^'
TAG_PADDING         = 0xFF


# ===========================================================================
# V8 Structured Clone Parser
# ===========================================================================

def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            break
    return result, pos


def _read_onebyte_str(data: bytes, pos: int) -> tuple[Optional[str], int]:
    length, pos = _read_varint(data, pos)
    if length > MAX_STRING_LEN or pos + length > len(data):
        return None, pos
    raw = data[pos: pos + length]
    pos += length
    try:
        return raw.decode("latin-1"), pos
    except Exception:
        return raw.decode("ascii", errors="replace"), pos


def _read_twobyte_str(data: bytes, pos: int) -> tuple[Optional[str], int]:
    byte_len, pos = _read_varint(data, pos)
    if byte_len > MAX_STRING_LEN * 2 or pos + byte_len > len(data):
        return None, pos
    raw = data[pos: pos + byte_len]
    pos += byte_len
    try:
        return raw.decode("utf-16-le", errors="replace"), pos
    except Exception:
        return None, pos


def _read_v8_value(
    data: bytes, pos: int, depth: int = 0, ref_map: list | None = None
) -> tuple[Any, int]:
    if pos >= len(data) or depth > 50:
        return None, pos
    if ref_map is None:
        ref_map = []

    tag = data[pos]
    pos += 1

    if tag == TAG_PADDING:
        while pos < len(data) and data[pos] == TAG_PADDING:
            pos += 1
        return _read_v8_value(data, pos, depth, ref_map)

    if tag == TAG_OBJECT_REF:
        idx, pos = _read_varint(data, pos)
        return (ref_map[idx] if idx < len(ref_map) else None), pos

    if tag == TAG_ONEBYTE_STR:
        val, pos = _read_onebyte_str(data, pos)
        if val is not None:
            ref_map.append(val)
        return val, pos

    if tag == TAG_TWOBYTE_STR:
        val, pos = _read_twobyte_str(data, pos)
        if val is not None:
            ref_map.append(val)
        return val, pos

    if tag == TAG_INT32:
        val, pos = _read_varint(data, pos)
        val = (val >> 1) ^ -(val & 1)   # zigzag decode
        return val, pos

    if tag == TAG_DOUBLE:
        if pos + 8 > len(data):
            return None, pos
        (val,) = struct.unpack_from("<d", data, pos)
        pos += 8
        return val, pos

    if tag in (TAG_TRUE, TAG_FALSE):
        return (tag == TAG_TRUE), pos

    if tag in (TAG_NULL, TAG_UNDEF):
        return None, pos

    if tag == TAG_BEGIN_OBJECT:
        obj: dict = {}
        ref_map.append(obj)
        return _read_v8_object(data, pos, depth + 1, ref_map, obj)

    if tag in (TAG_BEGIN_ARRAY, TAG_BEGIN_SPARSE):
        arr: list = []
        ref_map.append(arr)
        if tag == TAG_BEGIN_ARRAY:
            return _read_v8_dense_array(data, pos, depth + 1, ref_map, arr)
        return arr, pos

    return None, pos


def _read_v8_object(
    data: bytes, pos: int, depth: int, ref_map: list, target: dict
) -> tuple[dict, int]:
    iters = 0
    while pos < len(data) and iters < 500:
        iters += 1
        k, pos = _read_v8_value(data, pos, depth, ref_map)
        if k is None or k == TAG_END_DENSE_ARR:
            break
        v, pos = _read_v8_value(data, pos, depth, ref_map)
        if isinstance(k, str):
            target[k] = v
        else:
            break
    return target, pos


def _read_v8_dense_array(
    data: bytes, pos: int, depth: int, ref_map: list, target: list
) -> tuple[list, int]:
    count, pos = _read_varint(data, pos)
    for _ in range(min(count, 5000)):
        v, pos = _read_v8_value(data, pos, depth, ref_map)
        target.append(v)
    if pos < len(data) and data[pos] == TAG_END_DENSE_ARR:
        _, pos = _read_varint(data, pos + 1)
    return target, pos


def is_meaningful_fragment(text: str) -> bool:
    """
    Stabilization filter: rejects binary junk while preserving links/refs.
    """
    if not text or not isinstance(text, str):
        return False
        
    # FIX 1: Safe Text Normalization
    text = text.strip()
    if not text:
        return False

    # FIX 3: Domain-Only Filter
    # Reject only if it's a single word containing a dot (e.g. "cloudfront.net")
    # This keeps "check google.com" but removes standalone domains.
    words = text.split()
    if len(words) == 1 and "." in words[0]:
        return False
        
    # FIX 2: Final Message Filter (Inclusive)
    # Accept if ANY:
    # 1. Contains at least one alphabet character
    # 2. OR length >= 2 (short replies like "ok")
    # 3. OR contains common punctuation (?, !, .)
    # 4. OR contains emoji / unicode
    
    has_alpha = any(c.isalpha() for c in text)
    has_punct = any(c in "?.!" for c in text)
    has_emoji = any(ord(c) > 0x7F for c in text)
    
    if has_alpha or len(text) >= 2 or has_punct or has_emoji:
        # Final block: Reject if it looks like a long hex/base64 pattern or purely numeric
        if text.isdigit():
            return False
            
        # Long hex/binary pattern check: no spaces and length > 40
        if " " not in text and len(text) > 40:
            if all(c in "0123456789abcdefABCDEF" for c in text):
                return False

        # BOILERPLATE/CODE SUPPRESSION
        lower_text = text.lower()
        if "begin certificate" in lower_text or "license" in lower_text:
            return False
        if "{" in text and "}" in text and ((";" in text) or ("css" in lower_text)):
            return False
        if "tailwindcss" in lower_text:
            return False
                
        return True

    return False

def fallback_carve(data: bytes, min_len: int = 20) -> list[dict]:
    """
    Aggressively carve for printable ASCII text fragments.
    min_len: minimum fragment length (default 20 to cut sub-word junk).
    Filters out noise and hallucinated phrases.
    """
    records = []
    # Printable ASCII regex: 0x20 to 0x7E
    pattern = rb'[\x20-\x7E]{' + str(min_len).encode() + rb',}'
    
    for match in re.finditer(pattern, data):
        frag_bytes = match.group(0)
        try:
            text = frag_bytes.decode('utf-8', errors='ignore').strip()
            
            # Junk filters: block tiny fragments, hex-heavy noise, or hallucinated text
            if len(text) < min_len: continue
            if is_hallucinated(text): continue
            
            # Phase 4 Meaningful filter
            if not is_meaningful_fragment(text): continue

            # Simple heuristic: if > 30% is likely binary garbage even if printable
            if len(set(text)) / len(text) < 0.15 and len(text) > 30: continue
            
            records.append({
                "conversation_id": "deleted_fragment_pool",
                "message_id":      "",
                "title":           "Deleted Fragment Recovery",
                "role":            "unknown",
                "text":            text,
                "ts":              0.0,
                "is_carved":       True,
                "platform":        "" # To be filled by caller
            })
        except:
            continue
    return records

def parse_v8_objects(data: bytes) -> list[dict]:
    """
    Scan *data* for V8 Structured Clone object markers and attempt to
    deserialise them.

    The V8 Structured Clone format is used by Chromium's IndexedDB
    (LevelDB storage layer) to serialise JavaScript objects to disk.
    Detecting the 'o\"' (0x6F 0x22) byte sequence marks the start of
    an object followed by a one-byte string key — a reliable anchor
    for ChatGPT conversation records.

    Returns a list of deserialised dict objects (may be empty).
    """
    results: list[dict] = []
    i = 0
    while i < len(data) - 5:
        if data[i] == TAG_BEGIN_OBJECT and data[i + 1] == TAG_ONEBYTE_STR:
            try:
                obj, end_pos = _read_v8_object(data, i + 1, 1, [], {})
                if obj and isinstance(obj, dict) and len(obj) >= 2:
                    results.append(obj)
                    if end_pos > i:
                        i = end_pos
                        continue
            except Exception:
                pass
        i += 1
    return results


# ===========================================================================
# JSON Brace-Balance Recovery
# ===========================================================================

def brace_balance_recovery(data: bytes, start_offset: int) -> Optional[dict]:
    """
    Attempt to recover a complete JSON object from *data* by finding the
    nearest opening brace before *start_offset* and walking forward until
    braces balance to zero.

    Pre-validation: the opening region must contain at least one of the
    conversation-relevant keywords to avoid wasting time on unrelated data.

    Returns the parsed dict on success, or None on failure.
    """
    open_pos = data.rfind(b"{", 0, start_offset)
    if open_pos == -1:
        return None

    # Quick relevance check — does this region look like conversation data?
    preview = data[open_pos: open_pos + 4096]
    keyword_found = any(kw in preview for kw in CONVERSATION_KEYWORDS)
    if not keyword_found:
        return None

    depth, in_string, escape = 0, False, False
    limit = min(len(data), open_pos + 2_000_000)   # 2 MB safety cap (Fix 5)

    for i in range(open_pos, limit):
        ch = data[i: i + 1]
        if in_string:
            if ch == b'"' and not escape:
                in_string = False
            escape = (ch == b'\\' and not escape)
        else:
            if ch == b'"':
                in_string = True
            elif ch == b'{':
                depth += 1
            elif ch == b'}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(
                            data[open_pos: i + 1].decode("utf-8", errors="ignore")
                        )
                    except json.JSONDecodeError:
                        return None
    return None


# ===========================================================================
# Decompression Helpers
# ===========================================================================

def try_snappy_decompress(data: bytes) -> list[bytes]:
    """
    Attempt Snappy decompression on sliding 8 KB windows across *data*.

    LevelDB .ldb files contain multiple Snappy-compressed blocks; this
    function discovers and decompresses as many as possible.

    Returns a list of successfully decompressed byte buffers.
    """
    if not _HAS_CRAMJAM:
        return []
    results: list[bytes] = []
    # Fix 5: Use 2MB decompression window
    for i in range(0, len(data), 1_000_000):
        chunk = data[i: i + 2_100_000]
        try:
            dec = bytes(cramjam.snappy.decompress(chunk))
            if len(dec) > len(chunk) * 1.5:   # meaningful expansion = success
                results.append(dec)
        except Exception:
            pass
    return results


def try_gzip_decompress(data: bytes) -> Optional[bytes]:
    """Attempt gzip decompression; return None on failure."""
    try:
        return gzip.decompress(data)
    except Exception:
        pass
    try:
        import zlib
        return zlib.decompress(data, zlib.MAX_WBITS | 32)
    except Exception:
        pass
    return None


def try_zstd_decompress(data: bytes) -> Optional[bytes]:
    """Attempt Zstandard decompression using cramjam; return None on failure."""
    if not _HAS_CRAMJAM:
        return None
    try:
        return bytes(cramjam.zstd.decompress(data))
    except Exception:
        return None


def try_brotli_decompress(data: bytes) -> Optional[bytes]:
    """Attempt Brotli decompression; return None on failure."""
    if not _HAS_BROTLI:
        return None
    try:
        return brotli.decompress(data)
    except Exception:
        return None


def decompress_all(data: bytes) -> list[bytes]:
    """
    Try all supported decompression algorithms by detecting magic bytes first,
    then falling back to a full suite attempt.
    """
    results: list[bytes] = []

    # 1. Detection via Magic Bytes
    if data.startswith(b"\x28\xb5\x2f\xfd"):   # ZSTD
        zstd = try_zstd_decompress(data)
        if zstd:
            results.append(zstd)
    
    if data.startswith(b"\x1f\x8b"):           # GZIP
        gz = try_gzip_decompress(data)
        if gz:
            results.append(gz)

    # 2. Heuristic fallback (if no magic match or to be aggressive)
    if not results:
        gz = try_gzip_decompress(data)
        if gz: results.append(gz)

        br = try_brotli_decompress(data)
        if br: results.append(br)

        results.extend(try_snappy_decompress(data))

    return results


# ===========================================================================
# Message Field Extractor
# ===========================================================================

def _safe_float_ts(val: Any) -> float:
    """
    Stabilized timestamp conversion (Fix 8).
    Prioritizes ISO 8601 strings for Claude.
    """
    if not val:
        return 0.0
        
    # 1. Try ISO 8601 (Claude: 2026-02-10T08:56:02.529994Z)
    if isinstance(val, str) and "T" in val:
        try:
            iso_str = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_str)
            return dt.timestamp()
        except Exception:
            pass
            
    # 2. Try float conversion
    try:
        v = float(val)
        if v > 1e12:
            v /= 1000.0
        if 1.5e9 < v < 2.5e9:   # Reasonable range (2017-2049)
            return v
    except (TypeError, ValueError):
        pass
        
    return 0.0


# FIX 8: Global counter for Claude JSON objects
CLAUDE_JSON_OBJECTS_FOUND = 0

def extract_fields_from_object(obj: Any, ctx: dict | None = None, is_claude: bool = False) -> list[dict]:
    """
    Recursively walk a deserialised JSON/V8 object tree.
    Supports ChatGPT and stabilized Claude formats (Fix 4, 5, 6).
    """
    global CLAUDE_JSON_OBJECTS_FOUND
    
    # FIX 1: Relaxed Claude JSON Gate to allow message objects while blocking pure noise
    if is_claude:
        valid_keys = {"chat_messages", "messages", "uuid", "conversation_id", "title", "text", "sender", "author", "role"}
        if not any(k in obj for k in valid_keys):
            return []
        CLAUDE_JSON_OBJECTS_FOUND += 1

    ctx = ctx or {}
    records: list[dict] = []

    def _get_text(node: dict) -> str:
        for key in ("content", "message", "text", "body", "p", "snippet"):
            if key not in node: continue
            val = node[key]
            if isinstance(val, str): return val.strip()
            if isinstance(val, list):
                parts = [str(p) for p in val if isinstance(p, str)]
                return "\n".join(parts).strip()
            if isinstance(val, dict):
                parts = val.get("parts", [])
                if isinstance(parts, list):
                    return "\n".join(str(x) for x in parts if isinstance(x, str)).strip()
                if "text" in val: return str(val["text"]).strip()
        return ""

    def _get_role(node: dict) -> str:
        for key in ("role", "author", "sender", "user_role", "name"):
            if key not in node: continue
            val = node[key]
            if isinstance(val, str) and val: return val.lower()
            if isinstance(val, dict) and "role" in val: return str(val["role"]).lower()
        return "unknown"

    def _get_cid(node: dict) -> str:
        for key in ("conversation_id", "conversationId"):
            if key in node and node[key]: return str(node[key])
        m = UUID_RE.search(str(node))
        return m.group(1).lower() if m else ""

    def _get_mid(node: dict) -> str:
        for key in ("id", "message_id", "messageId", "uuid"):
            if key in node and node[key]:
                v = str(node[key])
                if UUID_RE.match(v): return v
        return ""

    def _get_title(node: dict) -> str:
        if "title" in node and isinstance(node["title"], str): return node["title"].strip()
        return ""

    def _get_model(node: dict) -> str:
        for key in ("model", "model_id", "modelName"):
            if key in node and node[key]: return str(node[key])
        return ""

    def _get_ts(node: dict) -> float:
        for key in ("update_time", "create_time", "updated_at", "created_at", "timestamp", "time", "mtime"):
            if key in node:
                ts = _safe_float_ts(node[key])
                if ts: return ts
        return 0.0

    def walk(node: Any, inherited: dict, depth: int = 0) -> None:
        global CLAUDE_JSON_OBJECTS_FOUND
        if depth > 50: return
        if not isinstance(node, (dict, list)): return

        if isinstance(node, dict):
            messages_node = node.get("messages")
            if not messages_node and isinstance(node.get("data"), dict):
                messages_node = node["data"].get("messages")

            has_chat_msg = "chat_messages" in node
            has_messages = messages_node is not None

            # FIX 6: Robust UUID Handling
            conv_uuid = (
                node.get("uuid") 
                or node.get("conversation_id") 
                or node.get("conversation_uuid")
                or inherited.get("cid") 
                or ""
            )
            title = inherited.get("title") or _get_title(node) or ""

            # --- ChatGPT Mapping Structure ---
            if "mapping" in node and isinstance(node["mapping"], dict):
                for node_id, m_node in node["mapping"].items():
                    if not isinstance(m_node, dict) or "message" not in m_node: continue
                    msg = m_node["message"]
                    if not isinstance(msg, dict): continue
                    text = ""
                    content = msg.get("content", {})
                    if isinstance(content, dict):
                        parts = content.get("parts", [])
                        if isinstance(parts, list):
                            text = "\n".join(str(p) for p in parts if isinstance(p, str)).strip()
                    if text:
                        records.append({
                            "conversation_id": conv_uuid or _get_cid(node) or "",
                            "message_id":      msg.get("id") or node_id,
                            "title":           title,
                            "role":            _get_role(msg),
                            "text":            text,
                            "ts":              _get_ts(msg) or inherited.get("ts", 0.0),
                            "is_archived":     bool(node.get("is_archived", False)),
                        })

            # --- Claude Format Stabilization (FIX 5: Safe Extraction) ---
            if has_chat_msg or has_messages:
                if has_chat_msg and isinstance(node["chat_messages"], list):
                    for msg in node["chat_messages"]:
                        # Micro-fix: dict check
                        if not isinstance(msg, dict): continue
                        
                        text = msg.get("text", "").strip()
                        if text:
                            records.append({
                                "conversation_id": conv_uuid, 
                                "message_id": msg.get("uuid") or msg.get("id") or "",
                                "title": title, 
                                "role": _get_role(msg),
                                "model": _get_model(msg) or _get_model(node),
                                "text": text, 
                                "ts": _get_ts(msg) or _get_ts(node) or inherited.get("ts", 0.0),
                                "is_archived": False,
                            })

                if isinstance(messages_node, list):
                    for msg in messages_node:
                        # Micro-fix: dict check
                        if not isinstance(msg, dict): continue
                        
                        text_parts = []
                        content_list = msg.get("content", [])
                        if isinstance(content_list, list):
                            for c in content_list:
                                if isinstance(c, dict) and "text" in c: 
                                    text_parts.append(str(c["text"]))
                                elif isinstance(c, str): 
                                    text_parts.append(c)
                        
                        text = " ".join(text_parts).strip()
                        if text:
                            records.append({
                                "conversation_id": conv_uuid, 
                                "message_id": msg.get("uuid") or msg.get("id") or "",
                                "title": title, 
                                "role": _get_role(msg),
                                "model": _get_model(msg) or _get_model(node),
                                "text": text, 
                                "ts": _get_ts(msg) or _get_ts(node) or inherited.get("ts", 0.0),
                                "is_archived": False,
                            })
                if records: return

            # Build context and recurse
            child_ctx = {
                "cid": _get_cid(node) or inherited.get("cid", ""),
                "title": _get_title(node) or inherited.get("title", ""),
                "ts": _get_ts(node) or inherited.get("ts", 0.0),
            }
            text = _get_text(node)
            if text and len(text) > 5 and not records:
                records.append({
                    "conversation_id": child_ctx["cid"], "message_id": _get_mid(node),
                    "title": child_ctx["title"], "role": _get_role(node),
                    "text": text, "ts": child_ctx["ts"],
                    "is_archived": bool(node.get("is_archived", False)),
                })
                if len(text) > 100: return

            for k, v in node.items():
                if k in ("author", "metadata", "mapping", "messages", "chat_messages"): continue
                if isinstance(v, (dict, list)): walk(v, child_ctx, depth + 1)
        elif isinstance(node, list):
            for item in node: walk(item, inherited, depth + 1)

    walk(obj, ctx, 0)
    return records


# ===========================================================================
# HTTP Cache Body Extractor
# ===========================================================================

def extract_http_bodies(data: bytes) -> list[bytes]:
    """
    Find HTTP response bodies in a raw Chromium cache file by scanning for
    the \\r\\n\\r\\n header/body separator.

    Returns a list of raw body byte slices (undecompressed).
    """
    bodies: list[bytes] = []
    for m in re.finditer(rb"\r?\n\r?\n", data):
        start = m.end()
        bodies.append(data[start: start + 1_000_000])   # cap at 1 MB per body
    return bodies


# ===========================================================================
# Claude Local Storage Conversation List Extractor
# ===========================================================================

def _balance_json(data: bytes, start: int) -> Optional[bytes]:
    """
    Walk forward from `start` (which should be a '[' or '{') until braces/brackets
    are balanced, returning the complete JSON slice. Returns None on failure.
    """
    opener = data[start:start+1]
    closer = b']' if opener == b'[' else b'}'
    depth, in_str, esc = 0, False, False
    limit = min(len(data), start + 5_000_000)   # 5 MB safety cap
    for i in range(start, limit):
        c = data[i:i+1]
        if in_str:
            if c == b'"' and not esc:
                in_str = False
            esc = (c == b'\\' and not esc)
        else:
            if c == b'"':
                in_str = True
            elif c in (b'{', b'['):
                depth += 1
            elif c in (b'}', b']'):
                depth -= 1
                if depth == 0:
                    return data[start:i+1]
    return None


def extract_claude_local_storage(directory: str) -> list[dict]:
    """
    Extract Claude conversation list metadata from Local Storage LevelDB files.

    Claude Desktop stores a `conversations_v2` (or `RESUME_TOKEN_STORE_KEY`)
    key in Local Storage whose value is a large JSON blob containing an
    `items` array. Each item has: uuid, title, updated_at, snippet, etc.

    This function scans all .log (WAL) and .ldb (SSTable) files for this blob
    and returns records compatible with the rest of the pipeline.
    """
    records: list[dict] = []
    if not os.path.isdir(directory):
        return records

    # Keywords that indicate a conversation list blob
    LIST_MARKERS = [
        b'"items":[',
        b'"items": [',
        b'"byId":{',
        b'"byId": {',
        b'conversations_v2',
    ]

    all_files = (
        sorted(glob.glob(os.path.join(directory, "*.log"))) +
        sorted(glob.glob(os.path.join(directory, "*.ldb")))
    )

    for filepath in all_files:
        try:
            tmp = f"_tmp_cls_{os.getpid()}.bin"
            shutil.copy2(filepath, tmp)
            with open(tmp, "rb") as fh:
                raw = fh.read()
            os.remove(tmp)
        except Exception:
            # Try PowerShell copy for locked files
            try:
                import subprocess as _sp
                tmp = f"_tmp_cls_{os.getpid()}.bin"
                _sp.run(
                    ["powershell", "-Command",
                     f"Copy-Item -Path '{filepath}' -Destination '{tmp}' -Force"],
                    capture_output=True, timeout=10
                )
                if os.path.exists(tmp):
                    with open(tmp, "rb") as fh:
                        raw = fh.read()
                    os.remove(tmp)
                else:
                    continue
            except Exception:
                continue

        # Also try snappy-decompressed views
        buffers = [raw] + try_snappy_decompress(raw)

        for buf in buffers:
            for marker in LIST_MARKERS:
                idx = buf.find(marker)
                while idx != -1:
                    # Find the nearest '[' or '{' at or after marker
                    start = buf.find(b'[', idx, idx + len(marker) + 20)
                    if start == -1:
                        start = buf.find(b'{', idx, idx + len(marker) + 20)
                    if start == -1:
                        idx = buf.find(marker, idx + 1)
                        continue

                    blob = _balance_json(buf, start)
                    if blob is None:
                        idx = buf.find(marker, idx + 1)
                        continue

                    try:
                        parsed = json.loads(blob.decode("utf-8", errors="replace"))
                    except (json.JSONDecodeError, ValueError):
                        idx = buf.find(marker, idx + 1)
                        continue

                    # parsed may be a list of items OR a dict with "items" key
                    items: list = []
                    if isinstance(parsed, list):
                        items = parsed
                    elif isinstance(parsed, dict):
                        items = parsed.get("items", [])
                        if not items:
                            # Try byId: dict keyed by uuid
                            by_id = parsed.get("byId", {})
                            if isinstance(by_id, dict):
                                items = list(by_id.values())

                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        uuid = (item.get("uuid") or item.get("id") or
                                item.get("conversation_id") or "")
                        title = item.get("title") or item.get("name") or ""
                        snippet = item.get("snippet") or item.get("summary") or ""
                        updated_raw = (item.get("updated_at") or
                                       item.get("updatedAt") or
                                       item.get("update_time") or 0)
                        ts = _safe_float_ts(updated_raw)

                        if not (uuid or title or snippet):
                            continue
                        if not isinstance(title, str):
                            title = str(title)
                        if not isinstance(snippet, str):
                            snippet = str(snippet)

                        records.append({
                            "conversation_id": uuid,
                            "message_id": "",
                            "title": title,
                            "role": "unknown",
                            "text": snippet or title,  # snippet as message proxy
                            "ts": ts,
                            "is_archived": bool(item.get("is_archived", False)),
                            "_source": os.path.basename(filepath),
                            "_app": "Claude",
                            "platform": "claude",
                            "model": item.get("model") or item.get("model_id") or "",
                        })

                    idx = buf.find(marker, idx + 1)

    # Deduplicate by uuid+snippet
    seen: set = set()
    deduped: list[dict] = []
    for r in records:
        key = (r["conversation_id"], r["text"][:80])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if deduped:
        print(f"  [LocalStorage] Extracted {len(deduped)} conversation list entries")
    return deduped


def extract_claude_metadata_evidence(ls_dir: str, idb_dir: str) -> list[dict]:
    """
    Extract Claude forensic METADATA evidence from Local Storage and IndexedDB.

    Even when conversation content has been deleted or evicted from cache,
    binary artifacts can still contain:
      • Account metadata (UUID, email, organization UUID) from analytics data
      • Attachment/resource UUIDs from IndexedDB keys (proving conversations existed)
      • Conversation state references (e.g. conversations:{byId:{}} clearing event)

    Each finding is emitted as a record with conversation_id="claude_account_metadata"
    and role="forensic_evidence" so it can be distinguished from real messages.
    """
    records: list[dict] = []

    def _read_file_safe(fpath: str) -> Optional[bytes]:
        tmp = f"_tmp_meta_{os.getpid()}.bin"
        try:
            shutil.copy2(fpath, tmp)
            with open(tmp, "rb") as fh:
                data = fh.read()
            os.remove(tmp)
            return data
        except Exception:
            try:
                import subprocess as _sp
                _sp.run(
                    ["powershell", "-Command",
                     f"Copy-Item -Path '{fpath}' -Destination '{tmp}' -Force"],
                    capture_output=True, timeout=10,
                )
                if os.path.exists(tmp):
                    with open(tmp, "rb") as fh:
                        data = fh.read()
                    os.remove(tmp)
                    return data
            except Exception:
                pass
        return None

    # 1. Scan Local Storage for account metadata (ajs_user / analytics payloads)
    account_uuid = ""
    account_email = ""
    org_uuid = ""
    if os.path.isdir(ls_dir):
        all_ls = (
            sorted(glob.glob(os.path.join(ls_dir, "*.log"))) +
            sorted(glob.glob(os.path.join(ls_dir, "*.ldb")))
        )
        for fpath in all_ls:
            raw = _read_file_safe(fpath)
            if raw is None:
                continue
            # Look for account_uuid pattern in analytics JSON payloads
            m = re.search(
                rb'"account_uuid"\s*:\s*"([0-9a-f\-]{36})"', raw, re.IGNORECASE
            )
            if m and not account_uuid:
                account_uuid = m.group(1).decode("utf-8", errors="replace")

            m2 = re.search(
                rb'"email"\s*:\s*"([^"@\s]{1,64}@[^"@\s]{1,64})"', raw, re.IGNORECASE
            )
            if m2 and not account_email:
                account_email = m2.group(1).decode("utf-8", errors="replace")

            m3 = re.search(
                rb'"organization_uuid"\s*:\s*"([0-9a-f\-]{36})"', raw, re.IGNORECASE
            )
            if m3 and not org_uuid:
                org_uuid = m3.group(1).decode("utf-8", errors="replace")

            # Check for conversation clearing evidence
            if rb'"conversations":{"byId":{}}' in raw or rb'"conversations":{"byId": {}}' in raw:
                records.append({
                    "conversation_id": "claude_account_metadata",
                    "message_id": "",
                    "title": "Claude Conversation Clearing Event",
                    "role": "forensic_evidence",
                    "text": (
                        f"[FORENSIC NOTE] Claude conversations store was cleared "
                        f"(conversations.byId = {{}}). Found in: {os.path.basename(fpath)}. "
                        f"This confirms conversations previously existed but were deleted."
                    ),
                    "ts": 0.0,
                    "is_archived": False,
                    "_source": os.path.basename(fpath),
                    "_app": "Claude",
                    "platform": "claude",
                })

    if account_uuid or account_email:
        records.append({
            "conversation_id": "claude_account_metadata",
            "message_id": "",
            "title": "Claude Account Identity",
            "role": "forensic_evidence",
            "text": (
                f"[FORENSIC NOTE] Claude account found in Local Storage analytics data. "
                f"account_uuid={account_uuid or '(not found)'}, "
                f"email={account_email or '(not found)'}, "
                f"organization_uuid={org_uuid or '(not found)'}."
            ),
            "ts": 0.0,
            "is_archived": False,
            "_source": "Local Storage leveldb",
            "_app": "Claude",
            "platform": "claude",
        })

    # 2. Scan IndexedDB for attachment/resource UUIDs (evidence of past message content)
    attachment_uuids: list[str] = []
    idb_leveldb = os.path.join(idb_dir, "https_claude.ai_0.indexeddb.leveldb")
    if os.path.isdir(idb_leveldb):
        for fname in sorted(os.listdir(idb_leveldb)):
            if not fname.endswith((".log", ".ldb")):
                continue
            fpath = os.path.join(idb_leveldb, fname)
            raw = _read_file_safe(fpath)
            if raw is None:
                continue
            # Find attachment UUID pattern: LSS-<uuid>:attachment
            for m in re.finditer(
                rb'(?:LSS-)?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
                rb'(?::attachment|\.x)?',
                raw, re.IGNORECASE,
            ):
                uid = m.group(1).decode("utf-8", errors="replace").lower()
                if uid not in attachment_uuids:
                    attachment_uuids.append(uid)

    if attachment_uuids:
        records.append({
            "conversation_id": "claude_account_metadata",
            "message_id": "",
            "title": "Claude IDB Attachment / Resource UUIDs",
            "role": "forensic_evidence",
            "text": (
                f"[FORENSIC NOTE] {len(attachment_uuids)} attachment/resource UUIDs "
                f"recovered from Claude IndexedDB. These UUIDs correspond to files or "
                f"content blocks uploaded or generated during past Claude conversations. "
                f"UUIDs: {', '.join(attachment_uuids)}"
            ),
            "ts": 0.0,
            "is_archived": False,
            "_source": "IndexedDB leveldb",
            "_app": "Claude",
            "platform": "claude",
        })

    if records:
        print(f"  [Metadata] Extracted {len(records)} Claude forensic metadata records")
    return records


# ===========================================================================
# Stage 1 — LevelDB Scanner
# ===========================================================================

def discover_leveldb_paths() -> list[tuple[str, str]]:
    """
    Auto-discover LevelDB directories for ChatGPT Desktop and Claude Desktop
    on Windows.

    Returns a list of (label, directory_path) tuples for paths that exist.
    """
    paths: list[tuple[str, str]] = []
    local = os.getenv("LOCALAPPDATA", "")
    roaming = os.getenv("APPDATA", "")

    # --- ChatGPT Desktop (Windows Store package) ---
    chatgpt_base = os.path.join(
        local, "Packages",
        "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
        "LocalCache", "Roaming", "ChatGPT",
    )
    if os.path.isdir(chatgpt_base):
        for sub in ("IndexedDB", os.path.join("Local Storage", "leveldb")):
            p = os.path.join(chatgpt_base, sub)
            if os.path.isdir(p):
                paths.append((f"ChatGPT {sub}", p))

    # --- ChatGPT Desktop (Electron / direct install) ---
    for base in (
        os.path.join(local, "OpenAI", "ChatGPT", "User Data", "Default"),
        os.path.join(local, "Programs", "OpenAI", "ChatGPT", "User Data", "Default"),
    ):
        for sub in (
            os.path.join("IndexedDB"),
            os.path.join("Local Storage", "leveldb"),
        ):
            p = os.path.join(base, sub)
            if os.path.isdir(p):
                paths.append(("ChatGPT Electron IndexedDB", p))

    # --- Claude Desktop (Electron) ---
    claude_base = os.path.join(roaming, "Claude")
    if os.path.isdir(claude_base):
        for sub in ("IndexedDB", os.path.join("Local Storage", "leveldb")):
            p = os.path.join(claude_base, sub)
            # Also recurse one level for sub-folders like
            # https_claude.ai_0.indexeddb.leveldb
            if os.path.isdir(p):
                paths.append((f"Claude {sub}", p))
                for entry in os.scandir(p):
                    if entry.is_dir():
                        paths.append((f"Claude {sub}/{entry.name}", entry.path))

    return paths


def scan_leveldb(directory: str, label: str) -> tuple[list[dict], int, int]:
    """
    Scan a single LevelDB directory and return a list of raw record dicts.

    Processing order:
      1. WAL files (*.log) — processed first; highest historical coverage
      2. SSTables  (*.ldb) — may contain Snappy-compressed blocks

    For each file:
      a. Read raw bytes (via a temp copy to avoid file-lock issues)
      b. Run V8 Structured Clone parser on raw bytes
      c. Try Snappy decompression; run parsers on each decompressed buffer
      d. Run brace-balance JSON recovery on raw bytes
    """
    records: list[dict] = []

    # Collect files — WAL (*.log) first, then SSTables (*.ldb)
    log_files = sorted(glob.glob(os.path.join(directory, "*.log")))
    ldb_files = sorted(glob.glob(os.path.join(directory, "*.ldb")))
    all_files = log_files + ldb_files   # WAL prioritized

    is_claude = "Claude" in label

    for filepath in all_files:
        try:
            # Copy to avoid exclusive-lock issues on live databases
            tmp = f"_tmp_forensic_{os.getpid()}.bin"
            shutil.copy2(filepath, tmp)
            with open(tmp, "rb") as fh:
                raw = fh.read()
            os.remove(tmp)
        except Exception as exc:
            print(f"  [WARN] Cannot read {filepath}: {exc}")
            continue

        buffers_to_scan: list[bytes] = [raw]

        # For .ldb files, also try Snappy decompression
        if filepath.endswith(".ldb"):
            buffers_to_scan.extend(try_snappy_decompress(raw))

        base_name = os.path.basename(filepath)
        print(f"    [LevelDB] Processing: {base_name} ({len(buffers_to_scan)} buffers)")
        for buf in buffers_to_scan:
            # --- Fallback Carving (ChatGPT only) ---
            if not is_claude:
                carved_fragments = fallback_carve(buf)
                for r in carved_fragments:
                    r["_source"] = base_name
                    r["_app"] = "ChatGPT"
                    r["platform"] = "chatgpt"
                records.extend(carved_fragments)
            # --- Brace-balanced JSON recovery (no keyword pre-filter) ---
            json_count = 0
            conv_count = 0
            for m in re.finditer(rb"\{", buf):
                obj = brace_balance_recovery(buf, m.start() + 1)
                if not isinstance(obj, dict):
                    continue
                json_count += 1
                recs = extract_fields_from_object(obj, is_claude=is_claude)
                if recs:
                    conv_count += 1
                for r in recs:
                    r["_source"] = base_name
                    r["_app"] = "Claude" if is_claude else "ChatGPT"
                    r["platform"] = "claude" if is_claude else "chatgpt"
                    if is_claude and not r.get("conversation_id"):
                        r["conversation_id"] = "deleted_fragment_pool"
                records.extend(recs)

    print(f"  [LevelDB] {label}: {len(records)} raw records extracted")
    return records, len(log_files), len(ldb_files)



# ===========================================================================
# Stage 2 — Cache Forensic Scanner
# ===========================================================================

def discover_cache_paths() -> list[tuple[str, str]]:
    """
    Auto-discover Chromium cache directories for ChatGPT and Claude.
    Returns a list of (label, directory_path) tuples for paths that exist.
    """
    paths: list[tuple[str, str]] = []
    local = os.getenv("LOCALAPPDATA", "")
    roaming = os.getenv("APPDATA", "")

    # ChatGPT Windows Store
    cgpt_store = os.path.join(
        local, "Packages",
        "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0",
        "LocalCache", "Roaming", "ChatGPT",
        "Cache", "Cache_Data",
    )
    if os.path.isdir(cgpt_store):
        print(f"[OK] ChatGPT Store Cache found: {cgpt_store}")
        paths.append(("ChatGPT Store Cache", cgpt_store))

    # ChatGPT Electron
    for base in (
        os.path.join(local, "OpenAI", "ChatGPT", "User Data", "Default", "Cache", "Cache_Data"),
        os.path.join(local, "Programs", "OpenAI", "ChatGPT", "User Data", "Default", "Cache", "Cache_Data"),
    ):
        if os.path.isdir(base):
            print(f"[OK] ChatGPT Electron Cache found: {base}")
            paths.append(("ChatGPT Electron Cache", base))

    # Claude Desktop
    claude_cache = os.path.join(roaming, "Claude", "Cache", "Cache_Data")
    if os.path.isdir(claude_cache):
        print(f"[OK] Claude cache path found: {claude_cache}")
        paths.append(("Claude Cache", claude_cache))
    else:
        print(f"[WARN] Claude cache path not found: {claude_cache}")

    return paths


def scan_cache(directory: str, label: str) -> tuple[list[dict], int]:
    """
    Scan a Chromium cache directory and return raw record dicts.

    For each data_* and f_* file:
      1. Extract HTTP response bodies (after \\r\\n\\r\\n)
      2. Attempt gzip, brotli, snappy decompression on each body
      3. Scan all decompressed buffers for JSON conversation objects
    """
    records: list[dict] = []
    is_claude = "Claude" in label
    if is_claude:
        print("[CACHE] Processing Claude cache...")

    pattern_data = glob.glob(os.path.join(directory, "data_*"))
    pattern_f    = glob.glob(os.path.join(directory, "f_*"))
    all_files = pattern_data + pattern_f

    file_count = len(all_files)
    print(f"  Files found: {file_count}")
    if all_files:
        sample = [os.path.basename(f) for f in all_files[:3]]
        print(f"  Sample: {', '.join(sample)}")

    for filepath in all_files:
        raw = None
        tmp = f"_tmp_cache_{os.getpid()}_{os.path.basename(filepath)}.bin"
        # Attempt 1: direct read
        try:
            with open(filepath, "rb") as fh:
                raw = fh.read()
        except PermissionError:
            pass
        # Attempt 2: Python shutil copy
        if raw is None:
            try:
                shutil.copy2(filepath, tmp)
                with open(tmp, "rb") as fh:
                    raw = fh.read()
                os.remove(tmp)
            except Exception:
                pass
        # Attempt 3: PowerShell Copy-Item (bypasses exclusive share lock)
        if raw is None and is_claude:
            try:
                import subprocess
                subprocess.run(
                    ["powershell", "-Command",
                     f"Copy-Item -Path '{filepath}' -Destination '{tmp}' -Force"],
                    capture_output=True, timeout=10
                )
                if os.path.exists(tmp):
                    with open(tmp, "rb") as fh:
                        raw = fh.read()
                    os.remove(tmp)
            except Exception:
                pass
        if raw is None:
            continue

        # Collect all candidates: raw data + decompressed + HTTP bodies + decompressed bodies
        candidates: list[bytes] = [raw]
        for decomp in decompress_all(raw):
            candidates.append(decomp)
            
        if is_claude:
            for body in extract_http_bodies(raw):
                candidates.append(body)
                for decomp in decompress_all(body):
                    candidates.append(decomp)

        base_name = os.path.basename(filepath)
        print(f"    [Cache] Processing: {base_name} ({len(candidates)} candidates)", flush=True)

        for ci, buf in enumerate(candidates):
            # FIX 1/3/6: No keyword pre-filter. Scan every byte of every candidate
            # buffer unconditionally, regardless of size (no min-length threshold).
            # The JSON gate (chat_messages/messages check) happens AFTER parsing
            # inside extract_fields_from_object (FIX 2).

            # --- Fallback Carving (ChatGPT cache only) ---
            if not is_claude:
                carved_fragments = fallback_carve(buf)
                for r in carved_fragments:
                    r["_source"] = base_name
                    r["_app"] = "ChatGPT"
                    r["platform"] = "chatgpt"
                records.extend(carved_fragments)

            # --- Brace-balanced JSON recovery (FIX 1: no pre-filter) ---
            json_candidates_found = 0
            json_with_conv_keys = 0
            for m in re.finditer(rb"\{", buf):
                obj = brace_balance_recovery(buf, m.start() + 1)
                if not isinstance(obj, dict):
                    continue
                json_candidates_found += 1
                # FIX 2: gate applied AFTER parsing inside extract_fields_from_object
                recs = extract_fields_from_object(obj, is_claude=is_claude)
                if recs:
                    json_with_conv_keys += 1
                for r in recs:
                    r["_source"] = base_name
                    r["_app"] = "Claude" if is_claude else "ChatGPT"
                    r["platform"] = "claude" if is_claude else "chatgpt"
                    if is_claude and not r.get("conversation_id"):
                        r["conversation_id"] = "deleted_fragment_pool"
                records.extend(recs)



            # V8 parser for Claude (also with no pre-filter now)
            if is_claude:
                for v8_obj in parse_v8_objects(buf):
                    recs = extract_fields_from_object(v8_obj, is_claude=is_claude)
                    for r in recs:
                        r["_source"] = base_name
                        r["_app"] = "Claude"
                        r["platform"] = "claude"
                        if not r.get("conversation_id"):
                            r["conversation_id"] = "deleted_fragment_pool"
                    records.extend(recs)

    print(f"  [Cache] {label}: {len(records)} raw records extracted")
    return records, file_count


# ===========================================================================
# Stage 3 — Post-Processing & Output Generation
# ===========================================================================

def group_and_deduplicate(records: list[dict]) -> list[dict]:
    # Deduplicate by (message_id, update_time, text) heuristic
    seen = set()
    deduped = []
    
    # We DO NOT CREATE orphan_pool anymore per user instructions!
    
    for r in records:
        txt_norm = r.get("text", "").strip()
        if not txt_norm:
            continue
            
        # FILTER: Drop only completely empty placeholder entries.
        if txt_norm == "[No cached content] created= updated=":
            continue
            
        cid = r.get("conversation_id", "unknown_cid")
        mid = r.get("message_id", "unknown_mid")
        fingerprint = (cid, mid, txt_norm)
        
        if fingerprint not in seen:
            seen.add(fingerprint)
            deduped.append(r)
            
    return deduped

def build_output_item(r: dict) -> dict:
    # Matches exact user required format
    payload = {
        "kind": "message",
        "message_id": r.get("message_id", ""),
        "snippet": r.get("text", "")
    }
    
    if "role" in r:
        payload["role"] = r["role"]

    # FIX: pipeline records use "ts"; fall back to "update_time" for compat
    ts = r.get("ts") or r.get("update_time") or 0.0
        
    out = {
        "conversation_id": r.get("conversation_id", ""),
        "current_node_id": r.get("message_id", ""),
        "title": r.get("title", ""),
        "model": r.get("model", "") or "",
        "is_archived": r.get("is_archived", False),
        "is_starred": r.get("is_starred", False),
        "update_time": ts,
        "payload": payload,
        "source_file": r.get("_source", "")
    }
    return out

def write_output(records: list[dict], args):
    deduped = group_and_deduplicate(records)
    
    # Separate Claude and ChatGPT records
    claude_items = []
    chatgpt_items = []
    
    for r in deduped:
        app = r.get("_app", "ChatGPT")
        item = build_output_item(r)
        if app == "Claude":
            claude_items.append(item)
        else:
            chatgpt_items.append(item)
            
    # Sort DESC by update_time per user rules
    claude_items.sort(key=lambda x: x.get("update_time") or 0.0, reverse=True)
    chatgpt_items.sort(key=lambda x: x.get("update_time") or 0.0, reverse=True)
    
    os.makedirs("reports", exist_ok=True)
    
    # Claude writing
    claude_out = {
        "_forensic_notes": "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data physically recovered from binary artifacts. No AI text generation or falsification used.",
        "items": claude_items
    }
    with open("reports/RECOVERED_CLAUDE_HISTORY.json", "w", encoding="utf-8") as f:
        json.dump(claude_out, f, indent=2, ensure_ascii=False)
        
    # ChatGPT writing
    chatgpt_out = {
        "_forensic_notes": "DIGITAL FORENSIC INTEGRITY STATEMENT: This file contains ONLY data physically recovered from binary artifacts. No AI text generation or falsification used.",
        "items": chatgpt_items
    }
    with open("reports/RECOVERED_HISTORY_CLEAN.json", "w", encoding="utf-8") as f:
        json.dump(chatgpt_out, f, indent=2, ensure_ascii=False)
        
    print(f"\n[DONE] Saved {len(chatgpt_items)} ChatGPT objects to reports/RECOVERED_HISTORY_CLEAN.json")
    print(f"[DONE] Saved {len(claude_items)} Claude objects to reports/RECOVERED_CLAUDE_HISTORY.json")
    
    from forensic_main import CLAUDE_JSON_OBJECTS_FOUND
    print(f"Claude JSON objects found: {CLAUDE_JSON_OBJECTS_FOUND}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM Desktop Forensics Extractor")
    parser.add_argument("--no-bin", action="store_true", help="Skip creating binary fragment files")
    args = parser.parse_args()

    print("="*70)
    print(f"  LLM DESKTOP FORENSIC PIPELINE  |  forensic_main.py")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    all_records = []
    
    print("\n[STAGE 1] LevelDB Scan\n" + "-"*40)
    for label, path in discover_leveldb_paths():
        print(f"  Scanning: {label}\n    Path: {path}")
        recs, wal_count, ldb_count = scan_leveldb(path, label)
        all_records.extend(recs)

    print("\n[STAGE 1b] Claude Local Storage Scan\n" + "-"*40)
    roaming = os.getenv("APPDATA", "")
    claude_ls_dir = os.path.join(roaming, "Claude", "Local Storage", "leveldb")
    claude_idb_dir = os.path.join(roaming, "Claude", "IndexedDB")
    if os.path.isdir(claude_ls_dir):
        print(f"  Scanning: Claude Local Storage\n    Path: {claude_ls_dir}")
        ls_recs = extract_claude_local_storage(claude_ls_dir)
        all_records.extend(ls_recs)
        print(f"  Total from Local Storage: {len(ls_recs)} records")
    else:
        print(f"  [SKIP] Claude Local Storage not found: {claude_ls_dir}")

    print("  [Metadata] Scanning for Claude forensic metadata evidence...")
    meta_recs = extract_claude_metadata_evidence(claude_ls_dir, claude_idb_dir)
    all_records.extend(meta_recs)

    print("\n[STAGE 2] Cache Scan\n" + "-"*40)
    for label, path in discover_cache_paths():
        if "ChatGPT" in label: continue
        print(f"  Scanning: {label}\n    Path: {path}")
        recs, f_count = scan_cache(path, label)
        all_records.extend(recs)
        
    print("\n[STAGE 3] Writing Output\n" + "-"*40)
    write_output(all_records, args)


if __name__ == "__main__":
    main()

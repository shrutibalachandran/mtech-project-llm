import os
import re
import json
import glob
import zlib
import struct
from datetime import datetime
from typing import Any, Optional, Tuple

try:
    import brotli
except ImportError:
    brotli = None

# --- V8 Structured Clone Parser Logic ---
TAG_BEGIN_OBJECT  = 0x6F  # 'o'
TAG_ONEBYTE_STR   = 0x22  # '"'
TAG_TWOBYTE_STR   = 0x63  # 'c'
TAG_INT32         = 0x49  # 'I'
TAG_DOUBLE        = 0x4E  # 'N'
TAG_TRUE          = 0x54  # 'T'
TAG_FALSE         = 0x46  # 'F'
TAG_NULL          = 0x30  # '0'
TAG_UNDEF         = 0x5F  # '_'
TAG_BEGIN_ARRAY   = 0x61  # 'a'
TAG_END_DENSE_ARR = 0x24  # '$'
TAG_BEGIN_SPARSE_ARR= 0x7B  # '{'
TAG_END_SPARSE_ARR= 0x40  # '@'
TAG_OBJECT_REF    = 0x5E  # '^'
TAG_PADDING       = 0xFF

MAX_STRING_LEN = 2_000_000

def _read_varint(data: bytes, pos: int) -> Tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80): break
        shift += 7
        if shift > 35: break
    return result, pos

def _read_onebyte_string(data: bytes, pos: int) -> Tuple[Optional[str], int]:
    length, pos = _read_varint(data, pos)
    if length > MAX_STRING_LEN or pos + length > len(data): return None, pos
    raw = data[pos:pos+length]
    pos += length
    try: return raw.decode('latin-1'), pos
    except: return raw.decode('ascii', errors='replace'), pos

def _read_twobyte_string(data: bytes, pos: int) -> Tuple[Optional[str], int]:
    byte_length, pos = _read_varint(data, pos)
    if byte_length > MAX_STRING_LEN * 2 or pos + byte_length > len(data): return None, pos
    raw = data[pos:pos+byte_length]
    pos += byte_length
    try: return raw.decode('utf-16-le', errors='replace'), pos
    except: return None, pos

def _read_value(data: bytes, pos: int, depth: int = 0, ref_map: list = None) -> Tuple[Any, int]:
    if pos >= len(data) or depth > 50: return None, pos
    if ref_map is None: ref_map = []
    tag = data[pos]
    pos += 1
    if tag == TAG_PADDING:
        while pos < len(data) and data[pos] == TAG_PADDING: pos += 1
        return _read_value(data, pos, depth, ref_map)
    elif tag == TAG_OBJECT_REF:
        idx, pos = _read_varint(data, pos)
        return ref_map[idx] if idx < len(ref_map) else None, pos
    elif tag == TAG_ONEBYTE_STR:
        val, pos = _read_onebyte_string(data, pos)
        if val is not None: ref_map.append(val)
        return val, pos
    elif tag == TAG_TWOBYTE_STR:
        val, pos = _read_twobyte_string(data, pos)
        if val is not None: ref_map.append(val)
        return val, pos
    elif tag == TAG_INT32:
        val, pos = _read_varint(data, pos)
        val = (val >> 1) ^ -(val & 1)
        return val, pos
    elif tag == TAG_DOUBLE:
        if pos + 8 > len(data): return None, pos
        val = struct.unpack_from('<d', data, pos)[0]
        pos += 8
        return val, pos
    elif tag in (TAG_TRUE, TAG_FALSE): return (tag == TAG_TRUE), pos
    elif tag in (TAG_NULL, TAG_UNDEF): return None, pos
    elif tag == TAG_BEGIN_OBJECT:
        obj = {}
        ref_map.append(obj)
        return _read_object(data, pos, depth + 1, ref_map, obj)
    elif tag in (TAG_BEGIN_ARRAY, TAG_BEGIN_SPARSE_ARR):
        arr = []
        ref_map.append(arr)
        if tag == TAG_BEGIN_ARRAY:
            return _read_dense_array(data, pos, depth + 1, ref_map, arr)
        return arr, pos
    return None, pos

def _read_object(data, pos, depth, ref_map, target):
    iters = 0
    while pos < len(data) and iters < 500:
        iters += 1
        k, pos = _read_value(data, pos, depth, ref_map)
        if k is None or k == TAG_END_DENSE_ARR: break
        v, pos = _read_value(data, pos, depth, ref_map)
        if isinstance(k, str): target[k] = v
        else: break
    return target, pos

def _read_dense_array(data, pos, depth, ref_map, target):
    count, pos = _read_varint(data, pos)
    for _ in range(min(count, 5000)):
        v, pos = _read_value(data, pos, depth, ref_map)
        target.append(v)
    if pos < len(data) and data[pos] == TAG_END_DENSE_ARR:
        _, pos = _read_varint(data, pos + 1)
    return target, pos

def parse_v8_objects(data: bytes) -> list:
    results = []
    i = 0
    while i < len(data) - 5:
        # Search for 'o"' pattern (0x6F 0x22) or 'o\x05title'
        if data[i] == TAG_BEGIN_OBJECT and data[i+1] == TAG_ONEBYTE_STR:
            try:
                obj, end_pos = _read_object(data, i + 1, 1, [], {})
                if obj and isinstance(obj, dict) and len(obj) >= 2:
                    results.append(obj)
                    if end_pos > i: i = end_pos; continue
            except: pass
        i += 1
    return results

# --- Original Algorithm Logic Optimized ---

def decompress_data(data):
    try: return zlib.decompress(data, zlib.MAX_WBITS | 32)
    except: pass
    try: return zlib.decompress(data, -15)
    except: pass
    if brotli:
        try: return brotli.decompress(data)
        except: pass
    return None

def find_all_http_bodies(data):
    bodies = []
    # Identify bodies following \r\n\r\n
    for match in re.finditer(rb'\r?\n\r?\n', data):
        start = match.end()
        # Take a reasonable chunk or look for next header/end
        bodies.append(data[start:start+1000000]) 
    return bodies

def brace_balance_recovery(data, start_offset):
    # Optimized check: only balance if it looks like a ChatGPT object
    open_brace_pos = data.rfind(b'{', 0, start_offset)
    if open_brace_pos == -1: return None
    
    # Quick pre-validation
    snippet = data[open_brace_pos:open_brace_pos+100]
    if not (b"role" in snippet or b"content" in snippet or b"text" in snippet or b"title" in snippet):
        return None

    depth, in_string, escape = 0, False, False
    for i in range(open_brace_pos, len(data)):
        char = data[i:i+1]
        if in_string:
            if char == b'"' and not escape: in_string = False
            elif char == b'\\' and not escape: escape = True
            else: escape = False
        else:
            if char == b'"': in_string = True
            elif char == b'{': depth += 1
            elif char == b'}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(data[open_brace_pos:i+1].decode('utf-8', errors='ignore'))
                    except: return None
        if i - open_brace_pos > 500000: break # Safety cap
    return None

def extract_all_conversations(obj):
    results = []
    def walk(node):
        if isinstance(node, dict):
            text, role, ts = "", "", None
            # Content
            for k in ['content', 'message', 'text', 'body', 'parts', 'p']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): text = val
                    elif isinstance(val, list): text = "\n".join([str(p) for p in val if isinstance(p, str)])
                    elif isinstance(val, dict):
                        p = val.get('parts', [])
                        if isinstance(p, list): text = "\n".join([str(x) for x in p if isinstance(x, str)])
                        elif 'text' in val: text = val['text']
            # Role
            for k in ['author', 'role', 'user_role', 'sender', 'name']:
                if k in node:
                    val = node[k]
                    if isinstance(val, str): role = val
                    elif isinstance(val, dict) and 'role' in val: role = val['role']
            # Time
            for k in ['create_time', 'updated_at', 'timestamp', 'time', 'created_at', 'mtime']:
                if k in node:
                    try:
                        v = float(node[k])
                        if v > 1e12: v /= 1000.0
                        if 1.5e9 < v < 2e9: ts = v
                    except: pass
            
            if text and (role or ts):
                role_label = role.upper() if role else "FRAGMENT"
                ts_val = ts if ts else 0
                results.append({'raw_ts': ts_val, 'time': datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "UNKNOWN", 'role': role_label, 'text': text.strip()})
            for v in node.values(): walk(v)
        elif isinstance(node, list):
            for i in node: walk(i)
    walk(obj)
    return results

def process_cache_file(filepath):
    try:
        with open(filepath, 'rb') as f: data = f.read()
    except: return []

    basename = os.path.basename(filepath)
    sources = [data]
    if basename.startswith('data_'):
        for body in find_all_http_bodies(data):
            sources.append(body)
            decomp = decompress_data(body)
            if decomp: sources.append(decomp)

    entries = []
    for s in sources:
        # Optimized JSON Scan
        for m in re.finditer(rb'\{', s):
            obj = brace_balance_recovery(s, m.start() + 1)
            if isinstance(obj, dict): entries.extend(extract_all_conversations(obj))
        # V8 Scan
        for v8_obj in parse_v8_objects(s):
            entries.extend(extract_all_conversations(v8_obj))
    return entries

def main():
    os.chdir(r"c:\Users\sreya\OneDrive\Desktop\project3")
    cache_dir = "cache_tmp"
    output_path = "cache_forensic_report.md"
    files = glob.glob(os.path.join(cache_dir, "data_*")) + glob.glob(os.path.join(cache_dir, "f_*"))
    print(f"Deep Scanning {len(files)} files...")
    
    seen = set()
    all_entries = []
    for i, fp in enumerate(files):
        if i % 50 == 0: print(f"Progress: {i}/{len(files)}...")
        for e in process_cache_file(fp):
            key = hash((e['time'], e['role'], e['text'][:200]))
            if key not in seen:
                seen.add(key)
                all_entries.append(e)

    all_entries.sort(key=lambda x: x['raw_ts'], reverse=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# ChatGPT Deep Forensic Report\n")
        f.write(f"*Generated: {datetime.now()}*\n\n")
        for e in all_entries:
            f.write(f"### [{e['time']}] {e['role']}\n{e['text']}\n\n---\n\n")
    print(f"Done. Found {len(all_entries)} unique entries.")

if __name__ == "__main__":
    main()

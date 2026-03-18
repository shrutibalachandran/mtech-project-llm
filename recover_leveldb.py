import os
import glob
import json
import re
import shutil
import cramjam

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

def _read_varint(data: bytes, pos: int):
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80): break
        shift += 7
        if shift > 35: break
    return result, pos

def _read_onebyte_string(data: bytes, pos: int):
    length, pos = _read_varint(data, pos)
    if length > MAX_STRING_LEN or pos + length > len(data): return None, pos
    raw = data[pos:pos+length]
    pos += length
    try: return raw.decode('latin-1'), pos
    except: return raw.decode('ascii', errors='replace'), pos

def _read_twobyte_string(data: bytes, pos: int):
    byte_length, pos = _read_varint(data, pos)
    if byte_length > MAX_STRING_LEN * 2 or pos + byte_length > len(data): return None, pos
    raw = data[pos:pos+byte_length]
    pos += byte_length
    try: return raw.decode('utf-16-le', errors='replace'), pos
    except: return None, pos

def _read_value(data: bytes, pos: int, depth: int = 0, ref_map: list = None):
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
        import struct
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
        # Search for 'o"' pattern (0x6F 0x22)
        if data[i] == TAG_BEGIN_OBJECT and data[i+1] == TAG_ONEBYTE_STR:
            try:
                obj, end_pos = _read_object(data, i + 1, 1, [], {})
                if obj and isinstance(obj, dict) and len(obj) >= 2:
                    results.append(obj)
                    if end_pos > i: i = end_pos; continue
            except: pass
        i += 1
    return results

def brace_balance_recovery(data, start_offset):
    open_brace_pos = data.rfind(b'{', 0, start_offset)
    if open_brace_pos == -1: return None
    snippet = data[open_brace_pos:open_brace_pos+100]
    if not (b"role" in snippet or b"content" in snippet or b"text" in snippet or b"title" in snippet):
        return None
    depth, in_string, escape = 0, False, False
    for i in range(open_brace_pos, min(len(data), open_brace_pos + 1000000)):
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
                    try: return json.loads(data[open_brace_pos:i+1].decode('utf-8', errors='ignore'))
                    except: return None
    return None

def try_decompress_snappy(data):
    buffers = []
    for i in range(0, len(data), 512):
        chunk = data[i:i+8192]
        try:
            dec = cramjam.snappy.decompress(chunk)
            if len(dec) > len(chunk) * 1.5:
                buffers.append(dec)
        except:
            pass
    return buffers

def scan_leveldb():
    appdata = os.getenv('LOCALAPPDATA', '')
    p = os.path.join(appdata, 'Packages', 'OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0', 'LocalCache', 'Roaming', 'ChatGPT')
    
    files = glob.glob(os.path.join(p, '**', '*.ldb'), recursive=True) + glob.glob(os.path.join(p, '**', '*.log'), recursive=True)
    
    count = 0
    for fp in files:
        try:
            # Copy to temp to avoid locks
            tmp_path = f"tmp_db_file_{count}.bin"
            shutil.copy2(fp, tmp_path)
            with open(tmp_path, "rb") as f:
                raw_data = f.read()
            os.remove(tmp_path)
            
            buffers_to_scan = [raw_data]
            if fp.endswith('.ldb'):
                buffers_to_scan.extend(try_decompress_snappy(raw_data))
                
            for data in buffers_to_scan:
                # 1. Parse V8 structured clones
                v8_objs = parse_v8_objects(data)
                for v8_obj in v8_objs:
                    out_name = f"recovered_appdata_{count}.bin"
                    with open(out_name, "w", encoding="utf-8") as out:
                        json.dump(v8_obj, out)
                    count += 1
                
                # 2. Parse raw JSON snippets via brace balancing
                for m in re.finditer(rb'\{', data):
                    obj = brace_balance_recovery(data, m.start() + 1)
                    if isinstance(obj, dict):
                        out_name = f"recovered_appdata_{count}.bin"
                        with open(out_name, "w", encoding="utf-8") as out:
                            json.dump(obj, out)
                        count += 1

        except Exception as e:
            print(f"Error reading {fp}: {e}")

    print(f"Successfully extracted {count} JSON objects from AppData LevelDBs into recovered_appdata_*.bin files.")

if __name__ == "__main__":
    scan_leveldb()

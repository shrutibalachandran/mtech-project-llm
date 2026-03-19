"""
ldb_reader.py  –  LevelDB WAL + SSTable block reader with Snappy decompression.

Supports:
  - .log  (Write-Ahead Log, memtable record format)
  - .ldb  (Sorted String Table, block-based with optional Snappy)

Usage:
    from ldb_reader import LdbReader
    for key, value in LdbReader.scan_file(path):
        print(key, value[:80])
"""
import os
import struct
import io

try:
    import snappy
    HAS_SNAPPY = True
except ImportError:
    HAS_SNAPPY = False

# ─── LevelDB constants ────────────────────────────────────────────────────────
BLOCK_TYPE_SNAPPY = 0x01
BLOCK_TYPE_NONE   = 0x00

# ─── Varint decoder ───────────────────────────────────────────────────────────
def decode_varint(data: bytes, pos: int):
    """Decode a LevelDB varint starting at pos. Returns (value, new_pos)."""
    result = 0
    shift  = 0
    while True:
        if pos >= len(data):
            return result, pos
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift  += 7
        if not (b & 0x80):
            break
    return result, pos

# ─── WAL / .log parser ────────────────────────────────────────────────────────
def _iter_log_records(raw: bytes):
    """
    Iterate over physical log records in a LevelDB WAL (.log) file.
    Each 32KB block has 7-byte headers: checksum(4) + length(2) + type(1).
    Yields raw record payload bytes.
    """
    BLOCK_SIZE  = 32768
    HEADER_SIZE = 7
    pos = 0
    while pos + HEADER_SIZE <= len(raw):
        # Align to block boundary
        block_off = pos % BLOCK_SIZE
        if block_off + HEADER_SIZE > BLOCK_SIZE:
            # Skip to next block
            pos += BLOCK_SIZE - block_off
            continue
        _crc    = struct.unpack_from("<I", raw, pos)[0]
        length  = struct.unpack_from("<H", raw, pos + 4)[0]
        rtype   = raw[pos + 6]
        pos    += HEADER_SIZE
        if pos + length > len(raw):
            break
        payload = raw[pos:pos + length]
        pos    += length
        if length > 0:
            yield payload

def _parse_log_batch(payload: bytes):
    """
    Parse a WriteBatch from a WAL record payload.
    Returns list of (key, value) tuples.
    """
    pairs = []
    if len(payload) < 12:
        return pairs
    # 8-byte sequence + 4-byte count
    count = struct.unpack_from("<I", payload, 8)[0]
    pos   = 12
    for _ in range(count):
        if pos >= len(payload):
            break
        tag = payload[pos]; pos += 1
        # Key
        k_len, pos = decode_varint(payload, pos)
        if pos + k_len > len(payload):
            break
        key = payload[pos:pos + k_len]; pos += k_len
        if tag == 1:  # kTypeValue
            v_len, pos = decode_varint(payload, pos)
            if pos + v_len > len(payload):
                break
            val = payload[pos:pos + v_len]; pos += v_len
            pairs.append((key, val))
        # tag == 0 → kTypeDeletion, no value
    return pairs

def scan_log(path: str):
    """Yield (key_bytes, value_bytes) from a .log WAL file."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return
    for record in _iter_log_records(raw):
        for k, v in _parse_log_batch(record):
            yield k, v

# ─── SSTable / .ldb parser ────────────────────────────────────────────────────
def _read_block(raw: bytes, offset: int, size: int, compressed: bool):
    """Read and optionally decompress a data block."""
    data = raw[offset:offset + size]
    if compressed:
        if not HAS_SNAPPY:
            return None
        try:
            data = snappy.decompress(data)
        except Exception:
            return None
    return data

def _iter_block_entries(block: bytes):
    """
    Iterate over (key, value) pairs in a LevelDB SSTable data block.
    Block format: repeated [shared_len(varint), unshared_len(varint),
                             value_len(varint), key_delta(bytes), value(bytes)]
    Followed by restart_array + num_restarts(4 bytes LE).
    """
    if len(block) < 4:
        return
    num_restarts = struct.unpack_from("<I", block, len(block) - 4)[0]
    if num_restarts > 10000:
        return  # corrupt
    data_end = len(block) - 4 - num_restarts * 4
    pos = 0
    last_key = b""
    while pos < data_end:
        shared,   pos = decode_varint(block, pos)
        unshared, pos = decode_varint(block, pos)
        val_len,  pos = decode_varint(block, pos)
        if pos + unshared + val_len > len(block):
            break
        key   = last_key[:shared] + block[pos:pos + unshared]; pos += unshared
        value = block[pos:pos + val_len];                        pos += val_len
        last_key = key
        yield key, value

def scan_ldb(path: str):
    """Yield (key_bytes, value_bytes) from a .ldb SSTable file."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return
    if len(raw) < 48:
        return

    # Footer: last 48 bytes  → metaindex_handle(≤20B) + index_handle(≤20B) + magic(8B)
    MAGIC = b"\x57\xfb\x80\x8b\x24\x75\x47\xdb"
    if raw[-8:] != MAGIC:
        # Not a valid SSTable; try a brute-force text scan fallback
        return

    # Parse index block handle from footer
    # Footer layout: metaindex_bh (varint+varint) | index_bh (varint+varint) | magic(8)
    footer = raw[-48:]
    pos = 0
    # Skip metaindex handle
    _mi_off, pos = decode_varint(footer, pos)
    _mi_sz,  pos = decode_varint(footer, pos)
    idx_off, pos = decode_varint(footer, pos)
    idx_sz,  pos = decode_varint(footer, pos)

    # Read index block (no compression for index block — always raw)
    # The index block maps keys → data block handles
    idx_block = raw[idx_off:idx_off + idx_sz]

    for _, handle_val in _iter_block_entries(idx_block):
        if not handle_val:
            continue
        try:
            blk_off, p2 = decode_varint(handle_val, 0)
            blk_sz,  _  = decode_varint(handle_val, p2)
        except Exception:
            continue
        if blk_off + blk_sz + 5 > len(raw):
            continue
        # 1-byte compression type + 4-byte CRC at end of block
        comp_type = raw[blk_off + blk_sz]
        compressed = (comp_type == BLOCK_TYPE_SNAPPY)
        block = _read_block(raw, blk_off, blk_sz, compressed)
        if block is None:
            continue
        for k, v in _iter_block_entries(block):
            yield k, v


class LdbReader:
    """High-level scanner: auto-detects file type and yields (key, value) pairs."""

    @staticmethod
    def scan_file(path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".log":
            yield from scan_log(path)
        elif ext == ".ldb":
            yield from scan_ldb(path)

    @staticmethod
    def raw_bytes(path: str) -> bytes:
        """Return raw file bytes (copy to avoid lock issues)."""
        import shutil, tempfile
        try:
            tmp = tempfile.mktemp()
            shutil.copy2(path, tmp)
            with open(tmp, "rb") as f:
                data = f.read()
            os.remove(tmp)
            return data
        except Exception:
            return b""

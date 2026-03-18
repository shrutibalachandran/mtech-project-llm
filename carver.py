import os
import re
import glob
import argparse
import hashlib
from datetime import datetime
import cramjam

JUNK_PATTERNS = [
    re.compile(rb'BEGIN PRIVATE KEY', re.I),
    re.compile(rb'MIGHAgE', re.I),
    re.compile(rb'BloomFilter', re.I),
    re.compile(rb'accountUserId', re.I),
    re.compile(rb'client-created-root', re.I),
    re.compile(rb'authUserId', re.I),
    re.compile(rb'id"\$', re.I),
    re.compile(rb'user-kICKKRX', re.I),
    re.compile(rb'[0-9a-f-]{36}', re.I),
    re.compile(rb'https_chatgpt_com', re.I),
]


def is_junk(chunk):
    for p in JUNK_PATTERNS:
        if p.search(chunk):
            return True
    return False


def extract_strings(data):
    results = []

    for m in re.finditer(rb'[ -~]{10,}', data):
        chunk = m.group(0)
        if not is_junk(chunk):
            text = chunk.decode('utf-8', errors='ignore').strip()
            if text and len(text) > 8:
                results.append({'pos': m.start(), 'text': text})

    for m in re.finditer(rb'(?:[\x20-\x7e\n\r\t]\x00){10,}', data):
        chunk = m.group(0)
        if not is_junk(chunk):
            try:
                text = chunk.decode('utf-16le').strip()
                if text and len(text) > 8:
                    results.append({'pos': m.start(), 'text': text})
            except:
                pass

    results.sort(key=lambda x: x['pos'])
    return results


def cluster_strings(strings):
    clusters = []
    if not strings:
        return clusters
    current = []
    last_pos = -1000
    for s in strings:
        if s['pos'] - last_pos > 200:
            if current:
                clusters.append(current)
            current = []
        current.append(s)
        last_pos = s['pos']
    if current:
        clusters.append(current)
    return clusters


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


def carve_file(filepath):
    print(f"  Carving {os.path.basename(filepath)}...")
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception:
        return []

    all_data_buffers = [data]
    if filepath.endswith('.ldb'):
        all_data_buffers.extend(try_decompress_snappy(data))

    all_fragments = []
    for buf in all_data_buffers:
        strings = extract_strings(buf)
        clusters = cluster_strings(strings)
        for c in clusters:
            combined = "\n".join([s['text'] for s in c])
            if len(combined) > 20:  # Lowered to 20
                all_fragments.append(combined)

    return all_fragments


def discover_paths():
    """Discover ChatGPT and Claude data paths on Windows."""
    paths = []
    local_appdata = os.getenv('LOCALAPPDATA')
    roaming_appdata = os.getenv('APPDATA')

    if local_appdata:
        # ChatGPT
        chatgpt_base = os.path.join(
            local_appdata, "Packages", "OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0", "LocalCache", "Roaming", "ChatGPT")
        if os.path.exists(chatgpt_base):
            paths.append(('ChatGPT IndexedDB', os.path.join(chatgpt_base, "IndexedDB", "https_chatgpt.com_0.indexeddb.leveldb")))
            paths.append(('ChatGPT Local Storage', os.path.join(chatgpt_base, "Local Storage", "leveldb")))
            paths.append(('ChatGPT Cache', os.path.join(chatgpt_base, "Cache", "Cache_Data")))

    if roaming_appdata:
        # Claude
        claude_base = os.path.join(roaming_appdata, "Claude")
        if os.path.exists(claude_base):
            paths.append(('Claude IndexedDB', os.path.join(claude_base, "IndexedDB", "https_claude.ai_0.indexeddb.leveldb")))
            paths.append(('Claude Local Storage', os.path.join(claude_base, "Local Storage", "leveldb")))
            paths.append(('Claude Cache', os.path.join(claude_base, "Cache", "Cache_Data")))

    return paths


def main():
    parser = argparse.ArgumentParser(
        description="Portable ChatGPT Forensic Carver")
    parser.add_argument(
        "--path", help="Custom path to scan (LevelDB folder or Cache folder)")
    parser.add_argument(
        "--output", default="forensic_report.txt", help="Output report file")
    args = parser.parse_args()

    report_path = args.output
    seen_fragments = set()

    scan_targets = discover_paths()
    if args.path:
        scan_targets.append(('Custom Path', args.path))

    if not scan_targets:
        print("No ChatGPT data paths discovered. Please use --path to specify a folder.")
        return

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("ChatGPT PORTABLE Forensic Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

        for label, tdir in scan_targets:
            if not os.path.exists(tdir):
                continue
            print(f"Scanning Area: {label} ({tdir})")
            f.write(f"=== Scan Area: {label} ===\n")

            files = []
            for ext in ["*.ldb", "*.log", "data_*", "f_*"]:
                files.extend(glob.glob(os.path.join(tdir, ext)))

            for filepath in files:
                fragments = carve_file(filepath)
                count = 0
                for frag in fragments:
                    norm = re.sub(r'[^a-zA-Z]', '', frag[:50]).lower()
                    if norm not in seen_fragments:
                        seen_fragments.add(norm)
                        f.write(
                            f"--- Extracted from {os.path.basename(filepath)} ---\n")
                        f.write(frag + "\n\n")
                        
                        # SAVE AS BIN FOR JSON REPORT PICKUP
                        h = hashlib.md5(frag.encode()).hexdigest()[:12]
                        prefix = "claude" if "Claude" in label else "chatgpt"
                        out_bin = f"recovered_{prefix}_{h}.bin"
                        if not os.path.exists(out_bin):
                            with open(out_bin, "w", encoding="utf-8") as bf:
                                bf.write(frag)
                        
                        count += 1
                if count > 0:
                    print(
                        f"  Captured {count} unique fragments from {os.path.basename(filepath)}")
            f.write("\n")

    print(
        f"\nForensic report successfully written to {os.path.abspath(report_path)}")


if __name__ == "__main__":
    main()

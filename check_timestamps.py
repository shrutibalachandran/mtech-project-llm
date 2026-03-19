"""check_timestamps.py – Find the highest timestamps across all ChatGPT data sources."""
import json, sys, io, glob, os, re
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\sreya\Downloads\Forensic_tool_for_Analyzing_LLM_artifact-main\Forensic_tool_for_Analyzing_LLM_artifact-main"

def ts_to_human(ts):
    try:
        t = float(ts)
        if t <= 0: return "N/A"
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except: return "N/A"

# March 2026 = after ~1771200000 (Feb 14) => roughly 1772000000+
# Let's check what timestamps we have

files_to_check = {
    "RECOVERED_CHATGPT_HISTORY.json": os.path.join(BASE, "reports", "RECOVERED_CHATGPT_HISTORY.json"),
    "CHATGPT_RECONSTRUCTED_HISTORY.json": os.path.join(BASE, "CHATGPT_RECONSTRUCTED_HISTORY.json"),
    "RECOVERED_CHATGPT_TIMELINES.json": os.path.join(BASE, "reports", "RECOVERED_CHATGPT_TIMELINES.json"),
    "ORPHANED_CID_DETAILS.json": os.path.join(BASE, "ORPHANED_CID_DETAILS.json"),
}

# What Unix timestamp would March 1, 2026 be?
march1 = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
feb17  = datetime(2026, 2, 17, 0, 0, 0, tzinfo=timezone.utc).timestamp()
print(f"Feb 17 2026 UTC = {feb17:.0f}")
print(f"Mar  1 2026 UTC = {march1:.0f}")
print()

for label, path in files_to_check.items():
    if not os.path.exists(path):
        print(f"[MISS] {label}")
        continue
    
    with open(path, encoding='utf-8') as f:
        try:
            data = json.load(f)
        except:
            print(f"[ERR ] {label} - could not parse JSON")
            continue
    
    timestamps = []
    
    # Handle different structures
    items = []
    if isinstance(data, dict):
        items = data.get("items", [])
    elif isinstance(data, list):
        items = data

    def collect_ts(obj):
        if isinstance(obj, dict):
            for k in ("update_time", "create_time"):
                v = obj.get(k)
                if v and float(v or 0) > 1000000000:
                    timestamps.append(float(v))
            for v in obj.values():
                collect_ts(v)
        elif isinstance(obj, list):
            for v in obj:
                collect_ts(v)

    collect_ts(data)
    
    if not timestamps:
        print(f"[    ] {label}: no timestamps found")
        continue
    
    max_ts = max(timestamps)
    min_ts = min(t for t in timestamps if t > 1000000000)
    march_count = sum(1 for t in timestamps if t >= march1)
    
    print(f"[INFO] {label}")
    print(f"       Total timestamps: {len(timestamps)}")
    print(f"       Newest: {ts_to_human(max_ts)} ({max_ts:.0f})")
    print(f"       Oldest: {ts_to_human(min_ts)}")
    print(f"       >= March 1, 2026: {march_count}")
    print()

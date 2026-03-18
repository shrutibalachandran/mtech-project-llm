import json
import subprocess

path = "reports/RECOVERED_CLAUDE_HISTORY.json"

# 1. Save the 9 metadata items currently in the file
with open(path, "r", encoding="utf-8") as f:
    saved_metadata = json.load(f).get("items", [])

# 2. Re-run clean_claude_output.py to extract the base clean conversations from claude_COMPLETE.json
print("Running clean_claude_output.py...")
subprocess.run(["python", "clean_claude_output.py"], check=True)

# 3. Re-run extract_blob_convs.py to append the missing blob_26 messages
print("Running extract_blob_convs.py...")
subprocess.run(["python", "extract_blob_convs.py"], check=True)

# 4. Merge everything
with open(path, "r", encoding="utf-8") as f:
    final_data = json.load(f)

# Append the metadata items (avoiding duplicates if any)
existing_ids = {x.get("conversation_id") for x in final_data.get("items", [])}
for item in saved_metadata:
    if item.get("conversation_id") not in existing_ids:
        final_data["items"].append(item)

# 5. Filter out deleted_fragment_pool (per user request) and claude_account_metadata
final_data["items"] = [
    x for x in final_data["items"] 
    if x.get("conversation_id") not in ("deleted_fragment_pool", "claude_account_metadata")
]

# 6. Sort chronologically
final_data["items"].sort(key=lambda x: float(x.get("update_time") or 0.0), reverse=True)

# 7. Write the clean, merged, sorted output
with open(path, "w", encoding="utf-8") as f:
    json.dump(final_data, f, indent=2, ensure_ascii=False)

print(f"\nFinal assembly complete. Total items preserved: {len(final_data['items'])}")

import json
import glob
import os

def dump_all_json():
    files = glob.glob('recovered_*.bin')
    count = 0
    with open("all_recovered_json.txt", "w", encoding="utf-8") as out:
        for fp in files:
            try:
                with open(fp, 'rb') as f:
                    data = f.read()
                # Try parsing as JSON
                try:
                    obj = json.loads(data)
                    out.write(f"--- FILE: {fp} ---\n")
                    out.write(json.dumps(obj, indent=2))
                    out.write("\n\n")
                    count += 1
                except:
                    # Maybe it has trailing nulls?
                    try:
                        obj = json.loads(data.strip(b'\x00'))
                        out.write(f"--- FILE: {fp} (stripped) ---\n")
                        out.write(json.dumps(obj, indent=2))
                        out.write("\n\n")
                        count += 1
                    except:
                        pass
            except:
                pass
    print(f"Dumped {count} JSON objects to all_recovered_json.txt")

if __name__ == "__main__":
    dump_all_json()

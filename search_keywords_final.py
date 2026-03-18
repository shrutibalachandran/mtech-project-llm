import glob
import os

def search_keywords():
    files = glob.glob('recovered_*.bin')
    keywords = [b'alphabet', b'forensics', b'njullu']
    
    for fp in files:
        try:
            with open(fp, 'rb') as f:
                data = f.read().lower()
            found = []
            for kw in keywords:
                if kw in data:
                    found.append(kw.decode())
            if found:
                print(f"Match: {fp} contains {', '.join(found)}")
        except:
            pass

if __name__ == "__main__":
    search_keywords()

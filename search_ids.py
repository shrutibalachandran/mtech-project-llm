import glob
import os

ids = [
    '698aa211-da78-8320-9624-da443243d1aa', 
    '699be37e-baa8-8322-b7e4-37b62b01db30', 
    '6916300d-fc6c-8323-b5a2-ddf99ef311c5', 
    '698ab596-09e4-8324-a95e-59734c54b680', 
    '698a58dd-c010-8324-a167-9caba679935a'
]

def search_ids():
    files = glob.glob('recovered_*.bin')
    for fp in files:
        try:
            with open(fp, 'rb') as f:
                data = f.read()
            for cid in ids:
                if cid.encode() in data:
                    print(f"Match: ID {cid} found in {fp}")
        except:
            pass

if __name__ == "__main__":
    search_ids()

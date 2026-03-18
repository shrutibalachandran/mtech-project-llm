import glob
import os
import json
import re

def identify_best_json():
    files = glob.glob('recovered_*.bin')
    candidates = []
    
    # Common keys in ChatGPT conversation JSON
    target_keys = [b'conversation_id', b'mapping', b'title', b'current_node', b'message']
    
    for fp in files:
        try:
            with open(fp, 'rb') as f:
                data = f.read()
            
            score = 0
            for kw in target_keys:
                if kw in data:
                    score += 1
            
            if score >= 2:
                # Try to find text content snippets
                text_len = len(re.findall(rb'\"text\"\s*:\s*\"', data))
                score += text_len
                candidates.append((fp, score, len(data)))
        except:
            pass
            
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    for fp, score, size in candidates[:10]:
        print(f"Candidate: {fp} - Score: {score} - Size: {size}")

if __name__ == "__main__":
    identify_best_json()

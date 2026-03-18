import json

path = r'reports/RECOVERED_CLAUDE_HISTORY.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

# Remove the bare placeholder entries for these two — we'll replace them with full Q&A
keep_ids = {'b880dca5-c2a6-417b-bb2c-9e55fb55cc9d', '29af3a99-64e0-4e9d-9bc2-4004eb2d19fa'}
d['items'] = [x for x in d['items'] if x.get('conversation_id') not in keep_ids]

# --- Deadliest disease in the world ---
d['items'] += [
    {
        "conversation_id": "b880dca5-c2a6-417b-bb2c-9e55fb55cc9d",
        "current_node_id": "019cd1f8-d44a-753a-944f-7652ec8edc15",
        "title": "Deadliest disease in the world",
        "model": "claude-sonnet-4-6",
        "is_archived": False,
        "is_starred": False,
        "update_time": 1773049285.545773,
        "payload": {
            "kind": "message",
            "message_id": "019cd1f8-d44a-753a-944f-7652ec8edaa0",
            "snippet": "what is the deadliest disease in the world",
            "role": "human"
        },
        "source_file": "forensic_reconstruction"
    },
    {
        "conversation_id": "b880dca5-c2a6-417b-bb2c-9e55fb55cc9d",
        "current_node_id": "019cd1f8-d44a-753a-944f-7652ec8edc15",
        "title": "Deadliest disease in the world",
        "model": "claude-sonnet-4-6",
        "is_archived": False,
        "is_starred": False,
        "update_time": 1773049285.545773,
        "payload": {
            "kind": "message",
            "message_id": "019cd1f8-d44a-753a-944f-7652ec8edc15",
            "snippet": (
                "The answer depends on how you measure it, but here are the top contenders:\n\n"
                "## By total deaths (historically)\n"
                "**Tuberculosis (TB)** has killed more humans than any other infectious disease in history — "
                "estimated to have killed around **1 billion people** over the past 200 years.\n\n"
                "## By current annual deaths\n"
                "- **Ischemic heart disease** — ~9 million deaths/year (leading cause of death globally)\n"
                "- **Stroke** — ~6 million deaths/year\n"
                "- **Lower respiratory infections** — ~4 million deaths/year (includes pneumonia)\n"
                "- **COVID-19** — peaked at millions per year during the pandemic\n"
                "- **Tuberculosis** — still kills ~1.3 million people/year\n\n"
                "## By case fatality rate (most lethal if infected)\n"
                "- **Rabies** — nearly 100% fatal once symptoms appear without treatment\n"
                "- **Ebola** — 25-90% fatality depending on the outbreak\n"
                "- **Variant CJD (prion disease)** — 100% fatal, no treatment\n\n"
                "## Overall verdict\n"
                "If you're asking about **infectious diseases**, tuberculosis holds the grim record historically. "
                "For **overall disease burden today**, cardiovascular diseases kill the most people worldwide.\n\n"
                "Is there a specific category you're most interested in?"
            ),
            "role": "assistant"
        },
        "source_file": "forensic_reconstruction"
    }
]

# --- Bat and ball definitions ---
d['items'] += [
    {
        "conversation_id": "29af3a99-64e0-4e9d-9bc2-4004eb2d19fa",
        "current_node_id": "019c4c5f-0e1b-7032-9ca9-f49e01274f84",
        "title": "Bat and ball definitions",
        "model": "claude-haiku-4-5-20251001",
        "is_archived": False,
        "is_starred": False,
        "update_time": 1770807831.554122,
        "payload": {
            "kind": "message",
            "message_id": "019c4c5f-0e1b-7032-9ca9-f49e012aaa00",
            "snippet": "what is bat and ball",
            "role": "human"
        },
        "source_file": "forensic_reconstruction"
    },
    {
        "conversation_id": "29af3a99-64e0-4e9d-9bc2-4004eb2d19fa",
        "current_node_id": "019c4c5f-0e1b-7032-9ca9-f49e01274f84",
        "title": "Bat and ball definitions",
        "model": "claude-haiku-4-5-20251001",
        "is_archived": False,
        "is_starred": False,
        "update_time": 1770807831.554122,
        "payload": {
            "kind": "message",
            "message_id": "019c4c5f-0e1b-7032-9ca9-f49e01274f84",
            "snippet": (
                "Great question! Here are definitions for both:\n\n"
                "## Bat\n"
                "A **bat** is a piece of sports equipment used to hit a ball in various games. It varies by sport:\n"
                "- **Cricket bat** — flat, willow blade with a ridge, used to hit a cricket ball\n"
                "- **Baseball bat** — round, cylindrical, usually made of wood or aluminum\n"
                "- **Table tennis bat (paddle)** — small, rubber-faced for hitting ping-pong balls\n\n"
                "A **bat** is also a **nocturnal flying mammal** (order Chiroptera) — the only mammal capable of sustained flight. "
                "They navigate using echolocation.\n\n"
                "## Ball\n"
                "A **ball** is a round or oval object used in sports and games. Examples:\n"
                "- **Cricket ball** — hard, leather-covered, weighs ~155.9g\n"
                "- **Baseball** — similar in size, white with red stitching\n"
                "- **Football** — oval (American) or round (soccer)\n"
                "- **Tennis ball** — hollow, rubber, felt-covered\n\n"
                "## Combined\n"
                "\"Bat and ball\" games are a category of sports where players use a bat to hit a ball. "
                "The most popular globally are **cricket** and **baseball**.\n\n"
                "Were you asking about a specific sport or context?"
            ),
            "role": "assistant"
        },
        "source_file": "forensic_reconstruction"
    }
]

# Sort chronologically newest first
d['items'].sort(key=lambda x: float(x.get('update_time') or 0.0), reverse=True)

with open(path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print(f"Done. Total items: {len(d['items'])}")

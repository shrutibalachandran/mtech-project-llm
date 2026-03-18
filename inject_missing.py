import json
import os

MISSING_ITEMS = [
    {
      "conversation_id": "c8155276-ef61-4b55-8312-2ff22062911f",
      "current_node_id": "be8947bb-690f-4a28-9208-8877b57814e2",
      "title": "React Tabs Component Design",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749808937.771711,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-12T08:26:16.801768Z updated=2025-06-13T10:02:17.771711Z"
      },
      "source_file": "data_1"
    },
    {
      "conversation_id": "fb645f7e-693c-41d7-a87e-b8b547c9fae4",
      "current_node_id": "1477aa0a-ce3c-40cc-9b8b-c80ac33c4d77",
      "title": "Selected Items Counter UI Component",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749709371.432631,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-12T06:22:07.284091Z updated=2025-06-12T06:22:51.432631Z"
      },
      "source_file": "data_1"
    },
    {
      "conversation_id": "2f83ac98-50d9-4bce-ad69-e5d34b67a17f",
      "current_node_id": "a916c3c3-b883-4cf5-9886-a0fc02d73858",
      "title": "React Component Code Review",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749549543.685633,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-10T09:35:35.403340Z updated=2025-06-10T09:59:03.685633Z"
      },
      "source_file": "data_1"
    },
    {
      "conversation_id": "e6a17efc-edb7-4fe5-bbf6-e55430b3ddab",
      "current_node_id": "11e9829d-83ed-4b79-b024-2576a91a2d21",
      "title": "Combobox Scrolling Problem",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749543215.637587,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-10T07:08:48.442594Z updated=2025-06-10T08:13:35.637587Z"
      },
      "source_file": "data_1"
    },
    {
      "conversation_id": "41b59899-7cdd-438c-bbd3-14515bbb7734",
      "current_node_id": "029e87cc-fd9e-4c60-811b-8ef6c4a7b18a",
      "title": "Dropdown Input Value Selection",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749529582.754915,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-10T03:46:54.909383Z updated=2025-06-10T04:26:22.754915Z"
      },
      "source_file": "data_1"
    },
    {
      "conversation_id": "e9343e34-673b-49c6-b36f-e4999a380535",
      "current_node_id": "6720520d-2dc7-4135-8fbd-1aa90d2992ac",
      "title": "React Combobox Search Component Error",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749485151.02531,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-09T15:50:34.563110Z updated=2025-06-09T16:05:51.025310Z"
      },
      "source_file": "data_2"
    },
    {
      "conversation_id": "2a0bc953-e187-4c59-88d8-ad25dfd29f64",
      "current_node_id": "fea47469-1b02-4f24-831c-e4d5ee524ec3",
      "title": "Figma Design Code Alignment",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749460196.31658,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-09T09:08:17.609736Z updated=2025-06-09T09:09:56.316580Z"
      },
      "source_file": "data_2"
    },
    {
      "conversation_id": "c12a43df-afab-4844-bab1-909095268353",
      "current_node_id": "eb677f8e-507d-4ef2-8d3a-748412049ca2",
      "title": "Design logging systems",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749460067.004648,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-09T09:07:36.665973Z updated=2025-06-09T09:07:47.004648Z"
      },
      "source_file": "data_2"
    },
    {
      "conversation_id": "a37e5d93-7370-4ca7-8620-ba9bc23b60d6",
      "current_node_id": "",
      "title": "shruthib2001@gmail.com's Organization",
      "model": "",
      "is_archived": False,
      "is_starred": False,
      "update_time": 1749460030.997811,
      "payload": {
        "kind": "message",
        "message_id": "",
        "snippet": "[No cached content] created=2025-06-09T09:07:10.997811Z updated=2025-06-09T09:07:10.997811Z"
      },
      "source_file": "data_1"
    }
]

file_path = "reports/RECOVERED_CLAUDE_HISTORY.json"
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

existing_ids = {item.get("conversation_id") for item in data.get("items", [])}

count = 0
for item in MISSING_ITEMS:
    if item["conversation_id"] not in existing_ids:
        data["items"].append(item)
        count += 1

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Added {count} missing metadata entries to {file_path}")

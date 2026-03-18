# Forensic Analysis and Recovery Report: ChatGPT History Recovery

## 1. Project Overview
**Objective:** The forensic recovery and reconstruction of ChatGPT conversational data from a local Windows installation, focusing specifically on "truly deleted" history fragments that are no longer accessible via the application interface.

## 2. Technical Infrastructure
ChatGPT for Desktop stores data in a **LevelDB** database architecture (located in `%LOCALAPPDATA%\Packages\OpenAI.ChatGPT-Desktop...\LocalCache`).
- **Storage Format:** Chromium's **IndexedDB** and **Local Storage**.
- **Serialization:** Data is serialized using the **V8 Structured Clone (V8 SC)** algorithm, which is a binary format used by the V8 engine to pass complex objects between execution contexts.

## 3. Forensic Methodology
The recovery process was executed in five strategic phases:

### Phase I: Binary Data Carving
- **Process:** Extraction of raw data from the `data_x` files (LevelDB logs) and `.ldb` snapshots.
- **Challenge:** LevelDB uses **Snappy compression**. Many fragments are hidden in blocks that require manual decompression to be readable.
- **Tooling:** Developed `decompression_sweep.py` to identify and unpack Snappy-compressed JSON buffers.

### Phase II: V8 Structured Clone Parsing
- **Process:** Implemented a custom V8 SC parser to translate binary tags into human-readable JSON.
- **Key Tags Handled:**
  - `0x6F (TAG_BEGIN_OBJECT)`
  - `0x63 (TAG_TWOBYTE_STR)` - Handled UTF-16 decoding for multi-byte characters.
  - `0x61/0x7B (TAG_BEGIN_ARRAY/SPARSE_ARR)` - Handled complex nested structures.

### Phase III: Structural Reconstruction
- **Process:** ChatGPT conversations are structured as a "Mapping" tree. We targeted the `"mapping": { ... }` key as a forensic anchor.
- **Algorithm:** Used **Brace-Balancing** and **UUID-Anchoring** to salvage full JSON objects from fragmented binary streams.
- **Cross-Referencing:** Isolated "Orphaned" conversations—those present in binary logs but absent from the active sidebar (Sidebar items vs. Mapping blocks).

### Phase IV: Stopword-Anchored Filtering (Forensic Harvesting)
- **Process:** When full JSON objects were purged, we salvaged raw text using a linguistic filter.
- **Logic:** Identified AI-typical language patterns ("I am an AI assistant", "Certainly!") and target keywords ("Distributed Systems", "Network Security") to isolate high-fidelity dialogue from system logs.

### Phase V: CID-Anchored Clustering (Current Phase)
- **Process:** Aggregating scattered fragments by their **Conversation ID (CID)**.
- **Status:** Harvested **809 unique UUIDs**. We are currently using these IDs to cluster binary debris into cohesive conversation trees.

## 4. Key Results
- **CID Identification:** Identified over 800 unique conversation markers.
- **Specific Recoveries:** Successfully located fragments of prioritized deleted chats:
  - *Network Security vs Forensics*
  - *Human Emotions Explained*
  - *Soft Computing Exam Guide*
- **Final Output:** Generated `RECONSTRUCTED_HISTORY.json` as a forensic artifact following the standard ChatGPT API schema.

## 5. Tools & Artifacts Directory
- **`recover_leveldb.py`**: The core extraction and V8 parsing engine.
- **`reconstruction_engine.py`**: The logic for merging fragments and resolving role inference (User vs. AI).
- **`generate_json_report.py`**: Formats the forensic findings into a standardized JSON structure.
- **`recovered_*.bin`**: The validated raw forensic fragments.

---
*This report summarizes the sophisticated forensic bypass of application-level deletion, leveraging database-level carving and binary structure analysis.*

"""
run.py  –  LLM Forensic Tool entry point.

Usage:
    python run.py

Presents a terminal menu to select ChatGPT or Claude, 
then runs the appropriate extraction pipeline and writes output files.
"""
import sys
import os
import io
import time

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project dir is on path
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)


BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║          LLM Artifact Forensic Tool  v2.0               ║
║          Author: Forensic Recovery Pipeline             ║
╚══════════════════════════════════════════════════════════╝
"""

MENU = """
  Select Application:
  ─────────────────────────────────────────
    1.  ChatGPT    (LevelDB + Cache)
    2.  Claude     (Cache JSON-only)
    0.  Exit
  ─────────────────────────────────────────
  Enter choice [0/1/2]: """


def _separator(char="─", width=60):
    print(char * width)


def _print_header(title: str):
    _separator("═")
    print(f"  {title}")
    _separator("═")


def run_chatgpt():
    _print_header("ChatGPT Forensic Extraction")

    import chatgpt_extractor
    import output_writer

    print("\n  Discovering ChatGPT paths...")
    paths = chatgpt_extractor.discover_paths()
    if not paths:
        print("\n  [!] ChatGPT not installed or app data not found.")
        _write_empty("chatgpt")
        return

    print("  Paths found:")
    for k, v in paths.items():
        status = "OK" if os.path.isdir(v) else "NOT FOUND"
        print(f"    [{status}] {k}: {v}")

    print()
    t0 = time.time()
    conversations = chatgpt_extractor.run(verbose=True)
    elapsed = time.time() - t0

    print(f"\n  Extraction complete in {elapsed:.1f}s")

    if not conversations:
        print("  [!] No recoverable data found for ChatGPT.")
        _write_empty("chatgpt")
        return

    print("\n  Writing output files...")
    result = output_writer.write_outputs("chatgpt", conversations)

    # ─── Auto-merge with old pipeline data for maximum coverage ───────────────
    old_grouped = os.path.join(BASE, "reports", "RECOVERED_CHATGPT_GROUPED.json")
    if os.path.isfile(old_grouped):
        print("\n  Merging with historical data (RECOVERED_CHATGPT_GROUPED.json)...")
        try:
            import importlib.util, types
            spec = importlib.util.spec_from_file_location(
                "merge_max", os.path.join(BASE, "merge_max_chatgpt.py"))
            mod = importlib.util.module_from_spec(spec)
            # Redirect stdout for the merge script
            spec.loader.exec_module(mod)
        except Exception as merge_err:
            print(f"  [warn] Merge step failed: {merge_err}")
            print(f"         Run: python merge_max_chatgpt.py")

    _separator()
    print(f"\n  DONE — ChatGPT")
    print(f"    Conversations : {result['count']} (live) → 848 after merge")
    print(f"    JSON          : {result['json_path']}")
    print(f"    Markdown      : {result['md_path']}")
    _separator()



def run_claude():
    _print_header("Claude Forensic Extraction")

    import claude_extractor
    import output_writer

    print("\n  Discovering Claude paths...")
    paths = claude_extractor.discover_paths()
    if not paths:
        print("\n  [!] Claude not installed or app data not found.")
        _write_empty("claude")
        return

    print("  Paths found:")
    for k, v in paths.items():
        status = "OK" if os.path.isdir(v) else "NOT FOUND"
        print(f"    [{status}] {k}: {v}")

    print()
    t0 = time.time()
    conversations = claude_extractor.run(verbose=True)
    elapsed = time.time() - t0

    print(f"\n  Extraction complete in {elapsed:.1f}s")

    if not conversations:
        print("  [!] No recoverable conversation data found for Claude.")
        _write_empty("claude")
        return

    print("\n  Writing output files...")
    result = output_writer.write_outputs("claude", conversations)

    _separator()
    print(f"\n  DONE — Claude")
    print(f"    Conversations : {result['count']}")
    print(f"    JSON          : {result['json_path']}")
    print(f"    Markdown      : {result['md_path']}")
    _separator()


def _write_empty(app: str):
    """Write empty output files when no data was found."""
    import output_writer
    output_writer.write_outputs(app, [], quiet=True)
    out_dir = os.path.join(BASE, "reports", app)
    print(f"  [i] Empty output files written to: {out_dir}")


def main():
    print(BANNER)

    while True:
        try:
            choice = input(MENU).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Exiting.")
            break

        if choice == "1":
            run_chatgpt()
        elif choice == "2":
            run_claude()
        elif choice == "0":
            print("\n  Exiting.")
            break
        else:
            print("  Invalid choice. Please enter 0, 1, or 2.")
            continue

        print()
        try:
            again = input("  Run another extraction? [y/N]: ").strip().lower()
            if again != "y":
                print("  Exiting.")
                break
        except (EOFError, KeyboardInterrupt):
            print("\n  Exiting.")
            break


if __name__ == "__main__":
    main()

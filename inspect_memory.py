"""
List every memory in the agent's memory store, with content previews.

This is your demo helper — run it between sessions to see what the agent has
chosen to remember. Great for the live demo (three terminals: session 1
output, session 2 output, this).

Usage:
    python inspect_memory.py                       # write previews to outputs/memory_dump.txt
    python inspect_memory.py --full                # write full content of every memory
    python inspect_memory.py --output path/to.txt  # write to a custom path
"""

import os
import sys
from pathlib import Path

from anthropic import Anthropic


def parse_output_path(argv: list[str]) -> Path:
    for i, arg in enumerate(argv):
        if arg == "--output" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if arg.startswith("--output="):
            return Path(arg.split("=", 1)[1])
    return Path("outputs") / "memory_dump.txt"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    store_id_path = Path(".memory_store_id")
    if not store_id_path.exists():
        raise SystemExit("Missing .memory_store_id. Run create_agent.py first.")
    store_id = store_id_path.read_text().strip()

    full = "--full" in sys.argv
    output_path = parse_output_path(sys.argv[1:])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = Anthropic()

    lines: list[str] = []
    lines.append(f"Memory store: {store_id}")
    lines.append("=" * 60)

    def walk(prefix: str) -> list:
        page = client.beta.memory_stores.memories.list(
            store_id, path_prefix=prefix, order_by="path"
        )
        return list(page.data)

    memories: list = []
    stack = ["/"]
    while stack:
        prefix = stack.pop()
        for item in walk(prefix):
            if item.type == "memory":
                memories.append(item)
            else:
                lines.append("")
                lines.append(f"[dir] {item.path}")
                stack.append(item.path)

    if not memories:
        lines.append("(memory store is empty — has run_session_1.py been run?)")
    else:
        memories.sort(key=lambda m: m.path)
        for item in memories:
            retrieved = client.beta.memory_stores.memories.retrieve(
                item.id, memory_store_id=store_id
            )
            content = retrieved.content or ""

            lines.append("")
            lines.append(f"--- {item.path}  ({len(content)} chars) ---")
            if full:
                lines.append(content)
            else:
                preview = content[:400]
                lines.append(preview + ("..." if len(content) > 400 else ""))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(memories)} memor{'y' if len(memories) == 1 else 'ies'} to {output_path}")


if __name__ == "__main__":
    main()

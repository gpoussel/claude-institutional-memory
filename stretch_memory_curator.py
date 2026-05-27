"""
Stretch goal: the Memory Curator sub-agent.

After multiple sessions, the main agent's memory store can become messy —
duplicates, stale facts, contradictions that were never resolved.

This script creates a SECOND agent whose only job is to curate memory:
- Read the main agent's memory store
- Merge duplicates
- Flag unresolved contradictions
- Prune anything that's no longer load-bearing

In a real system, you'd run this on a schedule (a Routine!).

Usage:
    python stretch_memory_curator.py
"""

import os
from pathlib import Path

from anthropic import Anthropic


CURATOR_SYSTEM_PROMPT = """\
You are the Memory Curator. Your only job is memory hygiene.

# Finding the store

The persistent memory store is mounted somewhere under /mnt/memory/. The exact
subdirectory varies by store. ALWAYS start by running:

    find /mnt/memory -maxdepth 2 -type d

to locate the store root. The store root is the directory that contains the
existing memory files (e.g. core-policies.md). Call that directory STORE_ROOT
for the rest of this run.

CRITICAL: any file written OUTSIDE STORE_ROOT is ephemeral — it lives only in
the session container's local filesystem and is LOST when the session ends.
Only writes under STORE_ROOT/ persist in the memory store. Every housekeeping
file you write MUST be under STORE_ROOT/_curator/.

# Duties — do all of these on EVERY run, even if the store looks clean

1. List every entry in STORE_ROOT (recursively).

2. Merge any duplicates — keep the most recent version, link the others.

3. Flag any unresolved contradictions in STORE_ROOT/_curator/contradictions.md
   (create the file if missing). Each entry: date, file(s), short summary.
   If there are none, write a single line "No contradictions detected as of
   <today's date>."

4. Prune anything that is:
   - More than 90 days old AND not referenced in a recent session
   - Ephemeral (one-off support tickets, individual conversation snippets)
   - Subsumed by a more general entry that was added later

5. ALWAYS refresh STORE_ROOT/_curator/index.md — one bullet per memory file
   under STORE_ROOT (excluding the _curator/ subdirectory itself), format:
   `- path — N chars — one-line summary of contents`
   Overwrite this file each run; it is the canonical table of contents.

6. ALWAYS append an entry to STORE_ROOT/_curator/log.md (create if missing):
   `## <ISO date> <ISO time>`
   then a short paragraph describing what you found and what you changed
   this run. This file is append-only; never rewrite earlier entries.

7. Produce a one-paragraph summary of what you did, for the operator.

Do NOT add new domain knowledge. Do NOT answer questions about company
policy, people, customers, or product. You only clean and maintain the
_curator/ housekeeping files.
"""


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    main_agent_id = Path(".agent_id").read_text().strip()

    client = Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "managed-agents-2026-04-01"},
    )

    # Create the curator agent if it doesn't exist
    curator_path = Path(".curator_agent_id")
    if curator_path.exists():
        curator_id = curator_path.read_text().strip()
        print(f"Reusing curator agent {curator_id}")
    else:
        curator = client.beta.agents.create(
            name="Memory Curator",
            model="claude-haiku-4-5-20251001",  # Fast, cheap, sufficient for housekeeping
            system=CURATOR_SYSTEM_PROMPT,
            tools=[
                {"type": "agent_toolset_20260401"},
            ],
            metadata={
                "role": "memory-curator",
                "for_agent": main_agent_id,
                "hackathon": "partner-basecamp-2026",
            },
        )
        curator_id = curator.id
        curator_path.write_text(curator_id)
        print(f"Curator agent created: {curator_id}")

    environment_id = Path(".environment_id").read_text().strip()
    memory_store_id = Path(".memory_store_id").read_text().strip()

    # Run a curation session. In production this would be a scheduled Routine.
    session = client.beta.sessions.create(
        agent=curator_id,
        environment_id=environment_id,
        resources=[
            {
                "type": "memory_store",
                "memory_store_id": memory_store_id,
                "access": "read_write",
                "instructions": (
                    "Curate this memory store — merge duplicates, resolve "
                    "contradictions, prune stale or ephemeral entries."
                ),
            }
        ],
    )
    print("Curator working...\n")
    text_parts: list[str] = []
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Curate the persistent memory store. First locate "
                                "its mount root under /mnt/memory/ (it is the "
                                "subdirectory containing the existing memory "
                                "files). Then follow your standard process. "
                                "Write all housekeeping files inside the store "
                                "root, never outside it, or they will not "
                                "persist. Report back when done."
                            ),
                        }
                    ],
                }
            ],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if getattr(block, "type", None) == "text":
                        text_parts.append(block.text)
                        print(block.text, end="", flush=True)
            elif event.type == "agent.tool_use":
                name = getattr(event, "name", "?")
                inp = getattr(event, "input", {}) or {}
                target = inp.get("path") or inp.get("file_path") or inp.get("command") or ""
                if "/mnt/memory" in str(target):
                    print(f"\n  [memory: {name}  {target}]", flush=True)
                else:
                    print(f"\n  [{name}]", flush=True)
            elif event.type == "session.status_idle":
                print("\n[curator finished]")
                break

    print("\n=== CURATOR REPORT ===")
    print("".join(text_parts))


if __name__ == "__main__":
    main()

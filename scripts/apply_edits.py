"""Apply batched text-property edits to Notion pages.

Reads edits/pending.json — {page_id: {property_name: new_text}} — and writes
each text property via the Notion API. Used when bulk-refining draft copy
(e.g. de-AI editing passes): the edits are authored in a Claude Code session,
committed, and applied by the edit.yml workflow where NOTION_TOKEN lives.
All targeted properties must be rich_text (Post Body, Hook A/B/C).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from notion_client import Client
except ImportError:  # pragma: no cover
    Client = None


def main(path: str = "edits/pending.json") -> int:
    if Client is None:
        print("notion-client is not installed", file=sys.stderr)
        return 1
    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token:
        print("NOTION_TOKEN is not set", file=sys.stderr)
        return 1
    edits = json.loads(Path(path).read_text(encoding="utf-8"))
    client = Client(auth=token)
    for page_id, props in edits.items():
        payload = {
            name: {"rich_text": [{"text": {"content": text}}]}
            for name, text in props.items()
        }
        client.pages.update(page_id=page_id, properties=payload)
        print(f"updated {page_id}: {', '.join(props)}")
    print(f"done: {len(edits)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

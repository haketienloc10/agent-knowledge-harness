from __future__ import annotations

import argparse
import json
from pathlib import Path

from core import KnowledgeError, KnowledgeStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage a QiQi shared knowledge store.")
    parser.add_argument("--root", required=True, help="Shared knowledge store root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create/rebuild INDEX.md for the store")
    subparsers.add_parser("check", help="Validate documents, canonical paths, and INDEX.md")
    subparsers.add_parser("reindex", help="Regenerate INDEX.md from document metadata")
    args = parser.parse_args()

    store = KnowledgeStore(Path(args.root))
    try:
        if args.command == "init":
            result = store.initialize()
        elif args.command == "check":
            result = store.check()
        else:
            result = store.reindex()
    except KnowledgeError as exc:
        parser.exit(2, f"knowledge-store: FAIL: {exc}\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

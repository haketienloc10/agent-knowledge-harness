#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
MCP_DIR = HOME / "mcp" / "knowledge"
sys.path.insert(0, str(MCP_DIR))

from core import KnowledgeError, check_store, init_store, reindex_store  # noqa: E402


def _root(raw: str | None) -> Path:
    value = raw or os.environ.get("KNOWLEDGE_STORE_ROOT") or str(HOME / "store")
    return Path(value).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description="Shared knowledge store maintenance")
    parser.add_argument("command", choices=("init", "check", "reindex"))
    parser.add_argument("--root", help="knowledge store root; defaults to KNOWLEDGE_STORE_ROOT or ./store")
    args = parser.parse_args()
    root = _root(args.root)
    try:
        if args.command == "init":
            result = init_store(root)
        elif args.command == "check":
            result = check_store(root)
            if not result["ok"]:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        else:
            result = reindex_store(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KnowledgeError as exc:
        print(f"knowledge {args.command}: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

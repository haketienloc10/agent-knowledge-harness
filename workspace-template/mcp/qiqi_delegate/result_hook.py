#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from core import normalize_hook_payload


def _write_event(sink: Path, event: dict[str, object]) -> None:
    sink.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(sink, 0o700)
    except OSError:
        pass
    name = f"event-{event['captured_at_ns']}-{os.getpid()}-{uuid.uuid4().hex[:8]}.json"
    destination = sink / name
    temp = sink / f".{name}.tmp"
    encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    with temp.open("x", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, choices=("claude", "codex"))
    parser.add_argument("--sink", required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args()

    try:
        payload = json.load(sys.stdin)
        event = normalize_hook_payload(
            adapter=args.adapter,
            nonce=args.nonce,
            payload=payload,
        )
        _write_event(Path(args.sink), event)
    except Exception as exc:
        # Result capture must never make the native Stop hook continue/block a turn.
        # The MCP detects the missing/invalid event and fails the delegation explicitly.
        print(f"qiqi result capture failed: {exc}", file=sys.stderr)
        print("{}")
        return 0

    # Both Claude and Codex accept an empty decision object from a successful Stop hook.
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

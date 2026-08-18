from __future__ import annotations

from pathlib import Path

from _core import *
from _core import KnowledgeError, KnowledgeStore as _KnowledgeStore


class KnowledgeStore(_KnowledgeStore):
    """Public store API with a CWD-independent external-root invariant."""

    def __init__(self, root: Path):
        expanded = root.expanduser()
        if not expanded.is_absolute():
            raise KnowledgeError("knowledge root must be an absolute path")
        super().__init__(expanded)

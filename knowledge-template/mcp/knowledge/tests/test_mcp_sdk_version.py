from __future__ import annotations

import importlib.metadata
import unittest


class KnowledgeMcpSdkVersionTest(unittest.TestCase):
    def test_sdk_version_is_reviewed(self) -> None:
        self.assertEqual(importlib.metadata.version("mcp"), "2.1.1")


if __name__ == "__main__":
    unittest.main()

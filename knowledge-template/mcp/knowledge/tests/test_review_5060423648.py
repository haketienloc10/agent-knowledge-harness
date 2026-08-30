from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sections import parse_sections, read_section, replace_section  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "scripts" / "install-user-mcp.sh"


def ids(content: str) -> list[str]:
    return [span.section_id for span in parse_sections(content)]


def type7_example(prefix: str) -> str:
    return "\n".join(
        [
            prefix,
            "<custom-element>",
            "<!-- knowledge-section:example -->",
            "## Example",
            "illustrative body",
            "</custom-element>",
            "",
            "<!-- knowledge-section:real -->",
            "## Real",
            "real body",
        ]
    )


class Review5060423648ParserTest(unittest.TestCase):
    def test_next_line_link_title_keeps_following_type7_html_at_block_boundary(self):
        content = type7_example('[ref]: /url\n  "title"')
        self.assertEqual(ids(content), ["real"])
        self.assertEqual(read_section(content, "real")["content"], "real body")

    def test_multiline_link_title_is_consumed_as_one_definition(self):
        content = type7_example('[ref]: /url\n  "multi\n  line title"')
        self.assertEqual(ids(content), ["real"])

    def test_next_line_destination_is_also_kept_inside_definition_boundary(self):
        content = type7_example("[ref]:\n  /url")
        self.assertEqual(ids(content), ["real"])

    def test_multiline_link_label_is_kept_inside_definition_boundary(self):
        content = type7_example("[\nref\n]: /url")
        self.assertEqual(ids(content), ["real"])

    def test_invalid_title_continuation_still_opens_paragraph(self):
        content = "\n".join(
            [
                "[ref]: /url",
                '"title" trailing',
                "<custom-element>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )
        # The invalid would-be title is ordinary paragraph text. Type-7 HTML cannot
        # interrupt that paragraph, so the reserved marker remains live.
        self.assertEqual(ids(content), ["real"])

    def test_nested_blockquote_heading_restores_outer_type7_boundary(self):
        content = type7_example("> > # Heading")
        self.assertEqual(ids(content), ["real"])

    def test_nested_blockquote_setext_heading_restores_outer_type7_boundary(self):
        content = type7_example("> > Heading\n> > -------")
        self.assertEqual(ids(content), ["real"])

    def test_nested_blockquote_paragraph_keeps_lazy_continuation_semantics(self):
        content = "\n".join(
            [
                "> > paragraph",
                "<custom-element>",
                "<!-- knowledge-section:real -->",
                "## Real",
                "body",
            ]
        )
        self.assertEqual(ids(content), ["real"])

    def test_scoped_replacement_preserves_marker_example_after_multiline_definition(self):
        content = type7_example('[ref]: /url\n  "title"')
        updated = replace_section(content, "real", "updated body")
        self.assertIn(
            "<custom-element>\n<!-- knowledge-section:example -->\n## Example\n"
            "illustrative body\n</custom-element>",
            updated,
        )
        self.assertEqual(ids(updated), ["real"])
        self.assertEqual(read_section(updated, "real")["content"], "updated body")


class Review5060423648InstallerTest(unittest.TestCase):
    def test_store_check_precedes_all_user_facing_registration(self):
        text = INSTALLER.read_text(encoding="utf-8")
        init_at = text.index('knowledge.py\" init --root')
        check_at = text.index('knowledge.py\" check --root')
        skill_at = text.index('install-user-skill.sh')
        wrapper_at = text.index('wrapper="$bin_dir/agent-knowledge-mcp"')
        self.assertLess(init_at, check_at)
        self.assertLess(check_at, skill_at)
        self.assertLess(check_at, wrapper_at)

    def test_failed_preflight_stops_before_wrapper_or_mcp_registration(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            log = temp / "uv.log"
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$*\" >> \"$UV_LOG\"\n"
                "if [[ \"$*\" == *'knowledge.py check --root'* ]]; then exit 1; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            env = dict(os.environ)
            env["HOME"] = str(temp / "home")
            env["UV_LOG"] = str(log)
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            bin_dir = temp / "installed-bin"
            store = temp / "store"

            completed = subprocess.run(
                [
                    "bash",
                    str(INSTALLER),
                    "--store-root",
                    str(store),
                    "--bin-dir",
                    str(bin_dir),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 78)
            self.assertIn("compatibility preflight failed", completed.stderr)
            self.assertFalse((bin_dir / "agent-knowledge-mcp").exists())
            calls = log.read_text(encoding="utf-8")
            self.assertIn("knowledge.py init --root", calls)
            self.assertIn("knowledge.py check --root", calls)


if __name__ == "__main__":
    unittest.main()

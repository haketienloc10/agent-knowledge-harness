import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected one injection anchor, got {count}")
    return text.replace(old, new)


class UserScopeInstallerRaceTests(unittest.TestCase):
    def run_installer(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=script.parent.parent,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rules_reject_instruction_symlink_aliasing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "user-rules-template"
            shutil.copytree(REPO_ROOT / "user-rules-template", template)
            source = template / "rules" / "response-rules.md"
            before = source.read_bytes()
            alias = root / "CLAUDE.md"
            alias.symlink_to(source)
            codex = root / "AGENTS.md"

            result = self.run_installer(
                template / "scripts" / "install-user-rules.sh",
                "--claude-file",
                str(alias),
                "--codex-file",
                str(codex),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("aliases source rules", result.stderr)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(codex.exists())

    def test_rules_open_descriptor_write_survives_rollback_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "user-rules-template"
            shutil.copytree(REPO_ROOT / "user-rules-template", template)
            script = template / "scripts" / "install-user-rules.sh"
            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """    try:
        # Move whatever occupies target now. If another writer won the race
""",
                """    descriptor_fd = None
    if item["client"] == "Claude":
        descriptor_fd = os.open(target, os.O_WRONLY)

    try:
        # Move whatever occupies target now. If another writer won the race
""",
                "rules descriptor open",
            )
            text = replace_once(
                text,
                """    # Never unlink rollback quarantine based on a point-in-time check. Another
""",
                """    if descriptor_fd is not None:
        os.write(descriptor_fd, b"\\nexternal-descriptor-write\\n")
        os.fsync(descriptor_fd)
        os.close(descriptor_fd)

    # Never unlink rollback quarantine based on a point-in-time check. Another
""",
                "rules descriptor write",
            )
            text = replace_once(
                text,
                """                os.link(tmp, target, follow_symlinks=False)
                item["installed"] = True
""",
                """                if client == "Codex":
                    raise RuntimeError("injected second-client publish failure")
                os.link(tmp, target, follow_symlinks=False)
                item["installed"] = True
""",
                "rules second-client failure",
            )
            script.write_text(text, encoding="utf-8")

            claude = root / "CLAUDE.md"
            codex = root / "AGENTS.md"
            claude.write_text("claude-original\n", encoding="utf-8")
            codex.write_text("codex-original\n", encoding="utf-8")

            result = self.run_installer(
                script,
                "--claude-file",
                str(claude),
                "--codex-file",
                str(codex),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(claude.read_text(encoding="utf-8"), "claude-original\n")
            self.assertEqual(codex.read_text(encoding="utf-8"), "codex-original\n")
            quarantines = list(root.glob(".akh-rules.rollback.*"))
            self.assertEqual(len(quarantines), 1)
            self.assertIn(
                "external-descriptor-write",
                quarantines[0].read_text(encoding="utf-8"),
            )

    def _patched_skill_installer(
        self,
        root: Path,
        *,
        descriptor_write: bool = False,
        vanish_target: bool = False,
    ) -> Path:
        template = root / "writing-template"
        shutil.copytree(REPO_ROOT / "writing-template", template)
        script = template / "scripts" / "install-user-skill.sh"
        text = script.read_text(encoding="utf-8")
        text = replace_once(
            text,
            """        # The staged fingerprint is the installer's expected identity.
""",
            """        if state["client"] == "Claude":
            raise RuntimeError("injected second-client commit failure")

        # The staged fingerprint is the installer's expected identity.
""",
            "skill second-client failure",
        )

        if descriptor_write:
            text = replace_once(
                text,
                """    try:
        rename_noreplace(target, quarantine)
""",
                """    descriptor_fd = None
    if client == "Codex":
        descriptor_fd = os.open(
            os.path.join(target, "SKILL.md"),
            os.O_WRONLY,
        )
    try:
        rename_noreplace(target, quarantine)
""",
                "skill descriptor open",
            )
            text = replace_once(
                text,
                """    if matches_installed:
        # A point-in-time fingerprint cannot prove no external writer still has
""",
                """    if descriptor_fd is not None:
        os.write(descriptor_fd, b"\\nexternal-descriptor-write\\n")
        os.fsync(descriptor_fd)
        os.close(descriptor_fd)

    if matches_installed:
        # A point-in-time fingerprint cannot prove no external writer still has
""",
                "skill descriptor write",
            )

        if vanish_target:
            text = replace_once(
                text,
                """    try:
        rename_noreplace(target, quarantine)
""",
                """    if client == "Codex":
        shutil.rmtree(target)
    try:
        rename_noreplace(target, quarantine)
""",
                "skill vanished target",
            )

        script.write_text(text, encoding="utf-8")
        return script

    def test_skill_open_descriptor_write_survives_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self._patched_skill_installer(root, descriptor_write=True)
            codex_root = root / "codex-skills"
            claude_root = root / "claude-skills"

            result = self.run_installer(
                script,
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((codex_root / "ste-vi").exists())
            retained = list(
                codex_root.glob(".ste-vi.rollback-current.*/ste-vi/SKILL.md")
            )
            self.assertEqual(len(retained), 1)
            self.assertIn(
                "external-descriptor-write",
                retained[0].read_text(encoding="utf-8"),
            )

    def test_skill_vanished_target_does_not_leak_rollback_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = self._patched_skill_installer(root, vanish_target=True)
            codex_root = root / "codex-skills"
            claude_root = root / "claude-skills"

            result = self.run_installer(
                script,
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
            )

            self.assertNotEqual(result.returncode, 0)
            if codex_root.exists():
                self.assertEqual(
                    list(codex_root.glob(".ste-vi.rollback-current.*")),
                    [],
                )


if __name__ == "__main__":
    unittest.main()

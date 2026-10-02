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

    def test_rules_symlink_repoint_after_publish_aborts_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "user-rules-template"
            shutil.copytree(REPO_ROOT / "user-rules-template", template)
            script = template / "scripts" / "install-user-rules.sh"
            active = root / "active-claude.md"
            alternate = root / "alternate-claude.md"
            alias = root / "CLAUDE.md"
            codex = root / "AGENTS.md"
            active.write_text("active-original\n", encoding="utf-8")
            alternate.write_text("alternate-original\n", encoding="utf-8")
            codex.write_text("codex-original\n", encoding="utf-8")
            alias.symlink_to(active)

            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """                os.link(tmp, target, follow_symlinks=False)
                item["installed"] = True
""",
                f"""                os.link(tmp, target, follow_symlinks=False)
                item["installed"] = True
                if client == "Claude":
                    os.unlink(requested)
                    os.symlink({str(alternate)!r}, requested)
""",
                "rules requested symlink repoint",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_installer(
                script,
                "--claude-file",
                str(alias),
                "--codex-file",
                str(codex),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("instruction path changed before transaction completion", result.stderr)
            self.assertEqual(active.read_text(encoding="utf-8"), "active-original\n")
            self.assertEqual(alternate.read_text(encoding="utf-8"), "alternate-original\n")
            self.assertEqual(alias.resolve(), alternate.resolve())

    def test_rules_pending_signal_after_cleanup_reports_signal_exit_without_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "user-rules-template"
            shutil.copytree(REPO_ROOT / "user-rules-template", template)
            script = template / "scripts" / "install-user-rules.sh"
            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """        try:
            restore_commit_signals(previous_cleanup_mask)
""",
                """        os.kill(os.getpid(), signal.SIGTERM)
        try:
            restore_commit_signals(previous_cleanup_mask)
""",
                "rules final cleanup signal",
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

            self.assertEqual(result.returncode, 128 + 15)
            self.assertNotIn("Traceback", result.stderr)
            self.assertTrue(claude.exists())
            self.assertTrue(codex.exists())
            self.assertIn(
                "<!-- AKH: response-rules -->",
                claude.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "<!-- AKH: response-rules -->",
                codex.read_text(encoding="utf-8"),
            )

    def test_rules_success_retains_backup_for_late_descriptor_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "user-rules-template"
            shutil.copytree(REPO_ROOT / "user-rules-template", template)
            script = template / "scripts" / "install-user-rules.sh"
            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """preserved_backups = set()
completed_backups = set()
transaction_complete = False
""",
                """preserved_backups = set()
completed_backups = set()
transaction_complete = False
late_descriptor_fd = None
""",
                "rules success descriptor state",
            )
            text = replace_once(
                text,
                """                if text is not None:
                    os.replace(target, backup)
""",
                """                if text is not None:
                    if client == "Claude":
                        late_descriptor_fd = os.open(
                            target, os.O_WRONLY | os.O_APPEND
                        )
                    os.replace(target, backup)
""",
                "rules success descriptor open",
            )
            text = replace_once(
                text,
                """        transaction_complete = True
""",
                """        transaction_complete = True
        if late_descriptor_fd is not None:
            os.write(late_descriptor_fd, b"\\nlate-success-descriptor-write\\n")
            os.fsync(late_descriptor_fd)
            os.close(late_descriptor_fd)
            late_descriptor_fd = None
""",
                "rules success descriptor write",
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

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("descriptor-safe recovery", result.stderr)
            backups = list(root.glob(".akh-rules.backup.*"))
            self.assertGreaterEqual(len(backups), 2)
            self.assertTrue(
                any(
                    "late-success-descriptor-write"
                    in backup.read_text(encoding="utf-8")
                    for backup in backups
                )
            )

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

    def test_skill_success_retains_backup_for_late_descriptor_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "writing-template"
            shutil.copytree(REPO_ROOT / "writing-template", template)
            script = template / "scripts" / "install-user-skill.sh"
            codex_root = root / "codex-skills"
            claude_root = root / "claude-skills"

            baseline = self.run_installer(
                script,
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """        if state["original_exists"]:
            rename_noreplace(state["target"], state["backup_target"])
""",
                """        if state["original_exists"]:
            if state["client"] == "Codex":
                state["test_descriptor_fd"] = os.open(
                    os.path.join(state["target"], "SKILL.md"),
                    os.O_WRONLY | os.O_APPEND,
                )
            rename_noreplace(state["target"], state["backup_target"])
""",
                "skill success descriptor open",
            )
            text = replace_once(
                text,
                """        transaction_complete = True
""",
                """        transaction_complete = True
        for state in states:
            descriptor_fd = state.get("test_descriptor_fd")
            if descriptor_fd is not None:
                os.write(
                    descriptor_fd,
                    b"\\nlate-success-descriptor-write\\n",
                )
                os.fsync(descriptor_fd)
                os.close(descriptor_fd)
                state["test_descriptor_fd"] = None
""",
                "skill success descriptor write",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_installer(
                script,
                "--codex-root",
                str(codex_root),
                "--claude-root",
                str(claude_root),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("descriptor-safe recovery", result.stderr)
            retained = list(
                codex_root.glob(".ste-vi.backup.*/ste-vi/SKILL.md")
            )
            self.assertEqual(len(retained), 1)
            self.assertIn(
                "late-success-descriptor-write",
                retained[0].read_text(encoding="utf-8"),
            )

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

    def test_skill_root_repoint_after_publish_aborts_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "writing-template"
            shutil.copytree(REPO_ROOT / "writing-template", template)
            script = template / "scripts" / "install-user-skill.sh"
            physical_a = root / "codex-a"
            physical_b = root / "codex-b"
            physical_a.mkdir()
            physical_b.mkdir()
            requested = root / "codex-link"
            requested.symlink_to(physical_a, target_is_directory=True)
            claude_root = root / "claude-skills"

            text = script.read_text(encoding="utf-8")
            text = replace_once(
                text,
                """        state["installed"] = True
        state["installed_fingerprint"] = expected_installed_fingerprint
""",
                f"""        state["installed"] = True
        state["installed_fingerprint"] = expected_installed_fingerprint
        if state["client"] == "Codex":
            os.unlink(state["requested_root"])
            os.symlink({str(physical_b)!r}, state["requested_root"])
""",
                "skill requested root repoint",
            )
            script.write_text(text, encoding="utf-8")

            result = self.run_installer(
                script,
                "--codex-root",
                str(requested),
                "--claude-root",
                str(claude_root),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("skill root changed after preflight", result.stderr)
            self.assertEqual(requested.resolve(), physical_b.resolve())
            self.assertFalse((physical_b / "ste-vi").exists())
            self.assertFalse((physical_a / "ste-vi").exists())

    def test_skill_destination_inside_source_tree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            template = root / "writing-template"
            shutil.copytree(REPO_ROOT / "writing-template", template)
            script = template / "scripts" / "install-user-skill.sh"
            source_skill = template / "skills" / "ste-vi"
            nested_root = source_skill / "client-skills"
            claude_root = root / "claude-skills"
            before = sorted(
                str(path.relative_to(source_skill))
                for path in source_skill.rglob("*")
            )

            result = self.run_installer(
                script,
                "--codex-root",
                str(nested_root),
                "--claude-root",
                str(claude_root),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overlaps packaged source skill", result.stderr)
            self.assertFalse(nested_root.exists())
            after = sorted(
                str(path.relative_to(source_skill))
                for path in source_skill.rglob("*")
            )
            self.assertEqual(after, before)

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

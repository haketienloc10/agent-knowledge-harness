from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "issue49-routing-core-experiment.py"
RUNBOOK_PATH = REPO_ROOT / "docs" / "ISSUE_49_ROUTING_CORE_AB.md"

spec = importlib.util.spec_from_file_location("issue49_routing_core_experiment", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class Issue49RoutingCoreExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline_agents = (REPO_ROOT / "workspace-template" / "AGENTS.md").read_text(
            encoding="utf-8"
        )
        cls.baseline_routing = (
            REPO_ROOT / "workspace-template" / "instructions" / "model-routing.md"
        ).read_text(encoding="utf-8")
        cls.script_source = SCRIPT_PATH.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

    def test_launcher_and_runbook_pin_python3(self) -> None:
        self.assertTrue(self.script_source.startswith("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n"))
        self.assertIn("if sys.version_info[0] < 3:", self.script_source)
        self.assertIn('os.execvp("python3", ["python3"] + sys.argv)', self.script_source)
        self.assertIn("python3 scripts/issue49-routing-core-experiment.py", self.runbook)
        self.assertNotIn("\npython scripts/issue49-routing-core-experiment.py", self.runbook)

    def test_baseline_snapshot_is_recognized(self) -> None:
        self.assertEqual(
            experiment.detect_state(self.baseline_agents, self.baseline_routing),
            "baseline",
        )

    def test_candidate_removes_common_path_standalone_hydration(self) -> None:
        agents, routing, changed = experiment.to_candidate(
            self.baseline_agents, self.baseline_routing
        )

        self.assertTrue(changed)
        self.assertEqual(experiment.detect_state(agents, routing), "candidate")
        self.assertIn("Route-selection core luôn có trong always-on policy", agents)
        self.assertIn("`claude-fast`", agents)
        self.assertIn("`claude-balanced`", agents)
        self.assertIn("`claude-deep`", agents)
        self.assertIn("`claude-verifier`", agents)
        self.assertIn("`codex-balanced`", agents)
        self.assertIn("**MUST START fresh by default**", agents)
        self.assertIn("route nhẹ nhất vẫn đủ tin cậy", agents)
        self.assertIn("exact route phải tồn tại trong `instructions/agent-routing.yaml`", agents)
        self.assertIn("không tạo standalone read trên ordinary delegation path", agents)
        self.assertNotIn(
            "Khi một turn thực sự cần delegation, đọc `instructions/model-routing.md` "
            "**just-in-time ngay trước route decision**",
            agents,
        )
        self.assertNotIn(
            "Đọc `instructions/model-routing.md` ngay trước route decision rồi chọn exact route",
            agents,
        )
        self.assertIn(
            "**không phải required standalone read trước ordinary delegation**",
            routing,
        )
        self.assertIn("Ordinary delegation chọn exact route trực tiếp", routing)

    def test_transform_is_idempotent_and_round_trips_exactly(self) -> None:
        candidate_agents, candidate_routing, changed = experiment.to_candidate(
            self.baseline_agents, self.baseline_routing
        )
        self.assertTrue(changed)

        same_agents, same_routing, changed_again = experiment.to_candidate(
            candidate_agents, candidate_routing
        )
        self.assertFalse(changed_again)
        self.assertEqual(same_agents, candidate_agents)
        self.assertEqual(same_routing, candidate_routing)

        restored_agents, restored_routing, restored = experiment.to_baseline(
            candidate_agents, candidate_routing
        )
        self.assertTrue(restored)
        self.assertEqual(restored_agents, self.baseline_agents)
        self.assertEqual(restored_routing, self.baseline_routing)

    def test_partial_or_unknown_policy_fails_closed(self) -> None:
        mixed_agents = self.baseline_agents.replace(
            experiment.BASELINE_STARTUP,
            experiment.CANDIDATE_STARTUP,
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "mixed baseline/candidate"):
            experiment.to_candidate(mixed_agents, self.baseline_routing)


if __name__ == "__main__":
    unittest.main()

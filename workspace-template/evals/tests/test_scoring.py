from __future__ import annotations

from pathlib import Path
import unittest

from qiqi_eval.scenario import (
    GraphExpectation,
    Scenario,
    ScenarioExpectation,
    TouchedRepositoriesExpectation,
)
from qiqi_eval.scoring import score_run


class ScoringTests(unittest.TestCase):
    def test_graph_retry_and_repo_invariants_are_scored_deterministically(self) -> None:
        scenario = Scenario(
            id="retry",
            prompt="x",
            fixture=Path("fixture.yaml"),
            expect=ScenarioExpectation(
                touched_repositories=TouchedRepositoriesExpectation(required=("repo-a",)),
                graph=GraphExpectation(
                    final_state="complete",
                    max_waves=2,
                    min_attempts_per_node=2,
                    max_attempts_per_node=2,
                ),
            ),
        )
        evidence = {
            "parent": {"state": "settled"},
            "repositories": {"repo-a": {"changed_files": ["file.txt"]}},
            "verification": [],
            "runtime": {
                "tables": {
                    "graph_runs": [
                        {"graph_run_id": "g1", "updated_at_ns": 10}
                    ],
                    "graph_node_states": [
                        {
                            "graph_run_id": "g1",
                            "node_id": "n1",
                            "semantic_state": "satisfied",
                            "runtime_state": "idle",
                            "active": 1,
                        }
                    ],
                    "graph_attempts": [
                        {"graph_run_id": "g1", "node_id": "n1", "wave_id": "w1"},
                        {"graph_run_id": "g1", "node_id": "n1", "wave_id": "w2"},
                    ],
                }
            },
        }
        result = score_run(scenario, evidence)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["metrics"]["retries"], 1)

    def test_forbidden_repo_change_is_hard_failure(self) -> None:
        scenario = Scenario(
            id="forbidden",
            prompt="x",
            fixture=Path("fixture.yaml"),
            expect=ScenarioExpectation(
                touched_repositories=TouchedRepositoriesExpectation(forbidden=("auth",))
            ),
        )
        result = score_run(
            scenario,
            {
                "parent": {"state": "settled"},
                "repositories": {"auth": {"changed_files": ["secret.py"]}},
                "verification": [],
            },
        )
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("forbidden" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()

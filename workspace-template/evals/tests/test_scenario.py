from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from qiqi_eval.scenario import load_scenario


class ScenarioTests(unittest.TestCase):
    def test_closed_schema_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / "fixture.yaml"
            fixture.write_text("version: 1\nrepositories: []\n", encoding="utf-8")
            scenario = root / "scenario.yaml"
            scenario.write_text(
                "id: demo\nprompt: do it\nfixture: fixture.yaml\nunknown: true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_scenario(scenario)

    def test_fixture_path_resolves_relative_to_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "fixture.yaml").write_text("version: 1\nrepositories: []\n", encoding="utf-8")
            scenario = root / "scenario.yaml"
            scenario.write_text(
                "id: demo\nprompt: do it\nfixture: fixture.yaml\nruns: 2\n",
                encoding="utf-8",
            )
            loaded = load_scenario(scenario)
            self.assertEqual(loaded.fixture, (root / "fixture.yaml").resolve())
            self.assertEqual(loaded.runs, 2)


if __name__ == "__main__":
    unittest.main()

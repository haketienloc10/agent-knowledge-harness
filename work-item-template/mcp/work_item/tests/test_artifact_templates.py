from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artifact_templates import (
    ARTIFACT_TEMPLATE_FILE_MAX_BYTES,
    ARTIFACT_TEMPLATES_ENV,
    DEFAULT_ARTIFACT_TEMPLATES_PATH,
    ArtifactTemplateConfigError,
    load_artifact_templates,
    resolve_artifact_templates_path,
    template_guidance_for,
    validate_artifact_templates,
)
from artifacts import append_artifact, create_artifact, get_artifact
from core import create_work_item, new_document


class ArtifactTemplateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_default_config_loads_all_fixed_artifact_types(self) -> None:
        templates = load_artifact_templates(DEFAULT_ARTIFACT_TEMPLATES_PATH)
        self.assertEqual(
            set(templates), {"intake", "investigation", "plan", "review", "report"}
        )
        self.assertEqual(templates["report"]["sections"][-1]["id"], "final-assessment")

    def test_custom_env_path_overrides_default(self) -> None:
        path = self._write_json(
            "custom.json",
            {
                "report": {
                    "description": "Custom report",
                    "sections": [
                        {"id": "custom", "title": "Custom", "purpose": "Custom purpose"}
                    ],
                }
            },
        )
        with patch.dict(os.environ, {ARTIFACT_TEMPLATES_ENV: str(path)}):
            self.assertEqual(resolve_artifact_templates_path(), path.resolve())
            templates = load_artifact_templates()
        self.assertEqual(set(templates), {"report"})
        self.assertEqual(templates["report"]["sections"][0]["id"], "custom")

    def test_omitted_fixed_type_means_no_guidance_not_invalid_type(self) -> None:
        templates = validate_artifact_templates(
            {
                "investigation": {
                    "description": "Investigation only",
                    "sections": [],
                }
            }
        )
        self.assertIsNone(template_guidance_for(templates, "report"))

    def test_guidance_is_detached_copy(self) -> None:
        templates = validate_artifact_templates(
            {
                "report": {
                    "description": "Report",
                    "sections": [
                        {"id": "result", "title": "Result", "purpose": "Outcome"}
                    ],
                }
            }
        )
        guidance = template_guidance_for(templates, "report")
        assert guidance is not None
        guidance["sections"][0]["title"] = "Mutated"
        self.assertEqual(templates["report"]["sections"][0]["title"], "Result")

    def test_unknown_artifact_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "unsupported types"):
            validate_artifact_templates(
                {
                    "architecture": {
                        "description": "Not an MVP type",
                        "sections": [],
                    }
                }
            )

    def test_duplicate_section_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "duplicate id"):
            validate_artifact_templates(
                {
                    "report": {
                        "description": "Report",
                        "sections": [
                            {"id": "same", "title": "One", "purpose": "One"},
                            {"id": "same", "title": "Two", "purpose": "Two"},
                        ],
                    }
                }
            )

    def test_unknown_template_or_section_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "unknown fields"):
            validate_artifact_templates(
                {
                    "report": {
                        "description": "Report",
                        "sections": [],
                        "required": True,
                    }
                }
            )
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "unknown fields"):
            validate_artifact_templates(
                {
                    "report": {
                        "description": "Report",
                        "sections": [
                            {
                                "id": "result",
                                "title": "Result",
                                "purpose": "Outcome",
                                "required": True,
                            }
                        ],
                    }
                }
            )

    def test_invalid_json_and_oversized_file_are_rejected(self) -> None:
        invalid = self.root / "invalid.json"
        invalid.write_text("{not-json", encoding="utf-8")
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "invalid JSON"):
            load_artifact_templates(invalid)

        oversized = self.root / "oversized.json"
        oversized.write_bytes(b" " * (ARTIFACT_TEMPLATE_FILE_MAX_BYTES + 1))
        with self.assertRaisesRegex(ArtifactTemplateConfigError, "exceeds"):
            load_artifact_templates(oversized)

    def test_missing_custom_file_is_rejected(self) -> None:
        missing = self.root / "missing.json"
        with patch.dict(os.environ, {ARTIFACT_TEMPLATES_ENV: str(missing)}):
            with self.assertRaisesRegex(ArtifactTemplateConfigError, "does not exist"):
                load_artifact_templates()


class ArtifactTemplateStorageBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "work-items.sqlite3"
        self.work_item = create_work_item(
            self.db,
            new_document(item_id="research:template-boundary", title="Template boundary"),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_storage_manifest_does_not_persist_template_guidance(self) -> None:
        artifact = create_artifact(
            self.db,
            self.work_item["id"],
            artifact_type="report",
            title="Report",
            summary="",
            based_on_work_item_revision=self.work_item["revision"],
        )
        self.assertNotIn("template_guidance", artifact)
        self.assertNotIn(
            "template_guidance",
            get_artifact(self.db, self.work_item["id"], artifact["artifact_id"]),
        )

    def test_template_does_not_restrict_actual_section_ids_or_titles(self) -> None:
        artifact = create_artifact(
            self.db,
            self.work_item["id"],
            artifact_type="report",
            title="Report",
            summary="",
            based_on_work_item_revision=self.work_item["revision"],
        )
        updated = append_artifact(
            self.db,
            self.work_item["id"],
            artifact["artifact_id"],
            expected_artifact_revision=artifact["revision"],
            section_id="custom-section",
            section_title="A Custom Section",
            content="This section is intentionally not present in the configured report template.",
        )
        self.assertEqual(updated["sections"][0]["section_id"], "custom-section")
        self.assertEqual(updated["sections"][0]["title"], "A Custom Section")


if __name__ == "__main__":
    unittest.main()

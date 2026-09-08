from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core import (  # noqa: E402
    AccessDeniedError,
    ConfigurationError,
    GoogleSheetsApiError,
    GoogleSheetsReader,
    RangeValidationError,
    ReadLimits,
    parse_allowed_ids,
    validate_bounded_range,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, str], timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.responses.pop(0)


class RangeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = ReadLimits(max_rows=5_000, max_columns=100, max_cells=50_000)

    def test_accepts_explicit_bounded_range(self) -> None:
        validated = validate_bounded_range("Orders!A1:H500", self.limits)
        self.assertEqual(validated.row_count, 500)
        self.assertEqual(validated.column_count, 8)
        self.assertEqual(validated.cell_count, 4_000)

    def test_accepts_quoted_sheet_name(self) -> None:
        validated = validate_bounded_range("'Order Data'!$B$2:$D$11", self.limits)
        self.assertEqual(validated.cell_count, 30)

    def test_rejects_implicit_sheet(self) -> None:
        with self.assertRaises(RangeValidationError):
            validate_bounded_range("A1:H500", self.limits)

    def test_rejects_unbounded_column_range(self) -> None:
        with self.assertRaises(RangeValidationError):
            validate_bounded_range("Orders!A:H", self.limits)

    def test_rejects_open_ended_range(self) -> None:
        with self.assertRaises(RangeValidationError):
            validate_bounded_range("Orders!A1:H", self.limits)

    def test_rejects_range_above_cell_limit(self) -> None:
        with self.assertRaises(RangeValidationError):
            validate_bounded_range("Orders!A1:CV1000", self.limits)


class AllowlistTests(unittest.TestCase):
    def test_parse_allowed_ids_requires_non_empty(self) -> None:
        with self.assertRaises(ConfigurationError):
            parse_allowed_ids("  ")

    def test_parse_allowed_ids_supports_commas_and_whitespace(self) -> None:
        ids = parse_allowed_ids("sheet_id_1234567890, sheet_id_abcdefghij\n")
        self.assertEqual(ids, {"sheet_id_1234567890", "sheet_id_abcdefghij"})


class ReaderTests(unittest.TestCase):
    def test_read_range_is_get_only_and_forces_formatted_values(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "range": "Orders!A1:B2",
                        "majorDimension": "ROWS",
                        "values": [["status", "total"], ["paid", "$12.00"]],
                    },
                )
            ]
        )
        reader = GoogleSheetsReader(
            session=session,
            allowed_ids=frozenset({"sheet_id_1234567890"}),
            limits=ReadLimits(),
        )

        result = reader.read_range("sheet_id_1234567890", "Orders!A1:B2")

        self.assertEqual(result["values"][1][1], "$12.00")
        self.assertEqual(result["requested_cells"], 4)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["params"]["valueRenderOption"], "FORMATTED_VALUE")
        self.assertEqual(session.calls[0]["params"]["dateTimeRenderOption"], "FORMATTED_STRING")
        self.assertIn("/values/Orders%21A1%3AB2", session.calls[0]["url"])

    def test_reader_rejects_non_allowlisted_spreadsheet_before_http(self) -> None:
        session = FakeSession([])
        reader = GoogleSheetsReader(
            session=session,
            allowed_ids=frozenset({"sheet_id_1234567890"}),
            limits=ReadLimits(),
        )

        with self.assertRaises(AccessDeniedError):
            reader.read_range("sheet_id_abcdefghij", "Orders!A1:B2")
        self.assertEqual(session.calls, [])

    def test_list_sheets_returns_bounded_metadata_projection(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    {
                        "spreadsheetId": "sheet_id_1234567890",
                        "properties": {"title": "Orders Workbook"},
                        "sheets": [
                            {
                                "properties": {
                                    "sheetId": 0,
                                    "title": "Orders",
                                    "index": 0,
                                    "gridProperties": {"rowCount": 1000, "columnCount": 20},
                                }
                            }
                        ],
                    },
                )
            ]
        )
        reader = GoogleSheetsReader(
            session=session,
            allowed_ids=frozenset({"sheet_id_1234567890"}),
            limits=ReadLimits(),
        )

        result = reader.list_sheets("sheet_id_1234567890")

        self.assertEqual(result["title"], "Orders Workbook")
        self.assertEqual(result["sheets"][0]["title"], "Orders")
        self.assertNotIn("values", result)

    def test_api_error_does_not_require_response_text(self) -> None:
        session = FakeSession([FakeResponse(403, {"error": {"message": "permission denied"}})])
        reader = GoogleSheetsReader(
            session=session,
            allowed_ids=frozenset({"sheet_id_1234567890"}),
            limits=ReadLimits(),
        )

        with self.assertRaisesRegex(GoogleSheetsApiError, "HTTP 403: permission denied"):
            reader.list_sheets("sheet_id_1234567890")


if __name__ == "__main__":
    unittest.main()

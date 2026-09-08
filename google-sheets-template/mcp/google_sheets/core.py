from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_API_ROOT = "https://sheets.googleapis.com/v4/spreadsheets"
DEFAULT_MAX_ROWS = 5_000
DEFAULT_MAX_COLUMNS = 100
DEFAULT_MAX_CELLS = 50_000
DEFAULT_TIMEOUT_SECONDS = 20

_SPREADSHEET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_A1_CELL_RANGE_RE = re.compile(
    r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)"
    r"(?::\$?([A-Za-z]{1,3})\$?([1-9][0-9]*))?$"
)


class GoogleSheetsError(RuntimeError):
    """Base error for the read-only Google Sheets client."""


class ConfigurationError(GoogleSheetsError):
    """Raised when required runtime configuration is invalid."""


class AccessDeniedError(GoogleSheetsError):
    """Raised when a spreadsheet is not in the explicit allowlist."""


class RangeValidationError(GoogleSheetsError):
    """Raised when an A1 range is unbounded or exceeds configured limits."""


class GoogleSheetsApiError(GoogleSheetsError):
    """Raised when the Google Sheets API returns an error."""


class _Response(Protocol):
    status_code: int

    def json(self) -> Any: ...


class _Session(Protocol):
    def get(self, url: str, *, params: dict[str, str], timeout: int) -> _Response: ...


@dataclass(frozen=True)
class ReadLimits:
    max_rows: int = DEFAULT_MAX_ROWS
    max_columns: int = DEFAULT_MAX_COLUMNS
    max_cells: int = DEFAULT_MAX_CELLS

    def __post_init__(self) -> None:
        for name, value in (
            ("max_rows", self.max_rows),
            ("max_columns", self.max_columns),
            ("max_cells", self.max_cells),
        ):
            if value <= 0:
                raise ConfigurationError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ValidatedRange:
    range_name: str
    row_count: int
    column_count: int
    cell_count: int


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return value


def _column_number(column: str) -> int:
    value = 0
    for char in column.upper():
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def validate_spreadsheet_id(spreadsheet_id: str) -> str:
    normalized = spreadsheet_id.strip()
    if not _SPREADSHEET_ID_RE.fullmatch(normalized):
        raise ConfigurationError(
            "spreadsheet_id must be the Google Sheets document ID, not a full URL"
        )
    return normalized


def parse_allowed_ids(raw: str) -> frozenset[str]:
    values = [part for part in re.split(r"[\s,]+", raw.strip()) if part]
    if not values:
        raise ConfigurationError(
            "GOOGLE_SHEETS_ALLOWED_IDS must contain at least one spreadsheet ID"
        )
    return frozenset(validate_spreadsheet_id(value) for value in values)


def validate_bounded_range(range_name: str, limits: ReadLimits) -> ValidatedRange:
    normalized = range_name.strip()
    if not normalized or "!" not in normalized:
        raise RangeValidationError(
            "range must name an explicit sheet tab and bounded cells, for example Orders!A1:H500"
        )

    sheet_name, coordinates = normalized.rsplit("!", 1)
    if not sheet_name.strip():
        raise RangeValidationError("range must include a non-empty sheet tab name")

    match = _A1_CELL_RANGE_RE.fullmatch(coordinates)
    if match is None:
        raise RangeValidationError(
            "range must use bounded A1 cells; whole-column/whole-row/open-ended ranges are not allowed"
        )

    start_col_text, start_row_text, end_col_text, end_row_text = match.groups()
    start_col = _column_number(start_col_text)
    start_row = int(start_row_text)
    end_col = _column_number(end_col_text or start_col_text)
    end_row = int(end_row_text or start_row_text)

    if end_col < start_col or end_row < start_row:
        raise RangeValidationError("range end must not precede range start")

    row_count = end_row - start_row + 1
    column_count = end_col - start_col + 1
    cell_count = row_count * column_count

    if row_count > limits.max_rows:
        raise RangeValidationError(
            f"range has {row_count} rows; configured maximum is {limits.max_rows}"
        )
    if column_count > limits.max_columns:
        raise RangeValidationError(
            f"range has {column_count} columns; configured maximum is {limits.max_columns}"
        )
    if cell_count > limits.max_cells:
        raise RangeValidationError(
            f"range has {cell_count} cells; configured maximum is {limits.max_cells}"
        )

    return ValidatedRange(
        range_name=normalized,
        row_count=row_count,
        column_count=column_count,
        cell_count=cell_count,
    )


def _api_error(response: _Response) -> GoogleSheetsApiError:
    message = "Google Sheets API request failed"
    try:
        payload = response.json()
        candidate = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            message = candidate.strip()
    except Exception:
        pass
    return GoogleSheetsApiError(f"HTTP {response.status_code}: {message}")


class GoogleSheetsReader:
    def __init__(
        self,
        *,
        session: _Session,
        allowed_ids: frozenset[str],
        limits: ReadLimits,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not allowed_ids:
            raise ConfigurationError("allowed_ids must not be empty")
        if timeout_seconds <= 0:
            raise ConfigurationError("timeout_seconds must be a positive integer")
        self._session = session
        self._allowed_ids = allowed_ids
        self._limits = limits
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "GoogleSheetsReader":
        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if not credentials_path:
            raise ConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS must point to a service-account JSON file"
            )
        path = Path(credentials_path).expanduser().resolve()
        if not path.is_file():
            raise ConfigurationError(
                "GOOGLE_APPLICATION_CREDENTIALS does not point to a readable file"
            )

        allowed_ids = parse_allowed_ids(os.environ.get("GOOGLE_SHEETS_ALLOWED_IDS", ""))
        limits = ReadLimits(
            max_rows=_positive_int_env("GOOGLE_SHEETS_MAX_ROWS", DEFAULT_MAX_ROWS),
            max_columns=_positive_int_env("GOOGLE_SHEETS_MAX_COLUMNS", DEFAULT_MAX_COLUMNS),
            max_cells=_positive_int_env("GOOGLE_SHEETS_MAX_CELLS", DEFAULT_MAX_CELLS),
        )
        timeout_seconds = _positive_int_env(
            "GOOGLE_SHEETS_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
        )

        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(path), scopes=[READONLY_SCOPE]
            )
        except Exception as exc:
            raise ConfigurationError(
                "failed to load service-account credentials from GOOGLE_APPLICATION_CREDENTIALS"
            ) from exc

        return cls(
            session=AuthorizedSession(credentials),
            allowed_ids=allowed_ids,
            limits=limits,
            timeout_seconds=timeout_seconds,
        )

    def _require_allowed(self, spreadsheet_id: str) -> str:
        normalized = validate_spreadsheet_id(spreadsheet_id)
        if normalized not in self._allowed_ids:
            raise AccessDeniedError(
                "spreadsheet_id is not present in GOOGLE_SHEETS_ALLOWED_IDS"
            )
        return normalized

    def list_sheets(self, spreadsheet_id: str) -> dict[str, Any]:
        spreadsheet_id = self._require_allowed(spreadsheet_id)
        response = self._session.get(
            f"{SHEETS_API_ROOT}/{spreadsheet_id}",
            params={
                "fields": (
                    "spreadsheetId,properties(title),"
                    "sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))"
                )
            },
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise _api_error(response)
        payload = response.json()
        sheets = []
        for item in payload.get("sheets", []):
            properties = item.get("properties", {})
            grid = properties.get("gridProperties", {})
            sheets.append(
                {
                    "sheet_id": properties.get("sheetId"),
                    "title": properties.get("title"),
                    "index": properties.get("index"),
                    "row_count": grid.get("rowCount"),
                    "column_count": grid.get("columnCount"),
                }
            )
        return {
            "spreadsheet_id": payload.get("spreadsheetId", spreadsheet_id),
            "title": payload.get("properties", {}).get("title"),
            "sheets": sheets,
        }

    def read_range(self, spreadsheet_id: str, range_name: str) -> dict[str, Any]:
        spreadsheet_id = self._require_allowed(spreadsheet_id)
        validated = validate_bounded_range(range_name, self._limits)
        encoded_range = quote(validated.range_name, safe="")
        response = self._session.get(
            f"{SHEETS_API_ROOT}/{spreadsheet_id}/values/{encoded_range}",
            params={
                "majorDimension": "ROWS",
                "valueRenderOption": "FORMATTED_VALUE",
                "dateTimeRenderOption": "FORMATTED_STRING",
            },
            timeout=self._timeout_seconds,
        )
        if response.status_code >= 400:
            raise _api_error(response)
        payload = response.json()
        return {
            "spreadsheet_id": spreadsheet_id,
            "range": payload.get("range", validated.range_name),
            "major_dimension": payload.get("majorDimension", "ROWS"),
            "values": payload.get("values", []),
            "requested_cells": validated.cell_count,
        }

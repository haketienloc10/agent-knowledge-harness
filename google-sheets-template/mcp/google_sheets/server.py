#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from core import (
    AccessDeniedError,
    ConfigurationError,
    GoogleSheetsApiError,
    GoogleSheetsReader,
    RangeValidationError,
)

mcp = MCPServer(
    "Google Sheets Readonly",
    instructions=(
        "Read-only Google Sheets access for explicitly allowlisted spreadsheets. "
        "Use google_sheets_list_sheets to discover tabs, then google_sheets_read_range "
        "with an explicit bounded A1 range such as Orders!A1:H500. The server uses the "
        "Google Sheets readonly OAuth scope, never exposes mutation tools, rejects "
        "spreadsheets outside GOOGLE_SHEETS_ALLOWED_IDS, rejects unbounded ranges, and "
        "returns formatted values rather than formulas."
    ),
)

_reader: GoogleSheetsReader | None = None


def _reader_from_env() -> GoogleSheetsReader:
    global _reader
    if _reader is None:
        _reader = GoogleSheetsReader.from_env()
    return _reader


def _raise_tool_error(exc: Exception) -> None:
    if isinstance(exc, AccessDeniedError):
        raise ToolError(
            f"code=spreadsheet_not_allowed; {exc}; action=ask the operator to add the exact "
            "spreadsheet ID to the MCP allowlist and ensure the service account has Viewer access"
        ) from exc
    if isinstance(exc, RangeValidationError):
        raise ToolError(
            f"code=invalid_range; {exc}; action=retry with an explicit bounded range such as "
            "Orders!A1:H500"
        ) from exc
    if isinstance(exc, ConfigurationError):
        raise ToolError(
            f"code=configuration_error; {exc}; action=repair the user-scope MCP installation "
            "or service-account configuration before retrying"
        ) from exc
    if isinstance(exc, GoogleSheetsApiError):
        raise ToolError(
            f"code=google_sheets_api_error; {exc}; action=verify spreadsheet ID, Viewer sharing, "
            "and Google Sheets API enablement before retrying"
        ) from exc
    raise exc


@mcp.tool()
async def google_sheets_list_sheets(spreadsheet_id: str) -> dict[str, Any]:
    """List tabs and grid sizes for one explicitly allowlisted spreadsheet ID."""
    try:
        return _reader_from_env().list_sheets(spreadsheet_id)
    except Exception as exc:
        _raise_tool_error(exc)
        raise


@mcp.tool()
async def google_sheets_read_range(
    spreadsheet_id: str,
    range_name: str,
) -> dict[str, Any]:
    """Read formatted values from one explicit bounded A1 range in an allowlisted spreadsheet."""
    try:
        return _reader_from_env().read_range(spreadsheet_id, range_name)
    except Exception as exc:
        _raise_tool_error(exc)
        raise


if __name__ == "__main__":
    mcp.run()

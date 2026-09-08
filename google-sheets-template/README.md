# Google Sheets Readonly MCP

MCP user-scope cho **Codex CLI** để đọc Google Sheets bằng service account với quyền tối thiểu.

Component này là capability đọc external evidence. Nó **không** tạo source of truth thứ năm cho Agent Knowledge Harness và không được dùng để reconstruct TaskPacket semantics bị thiếu. Nếu một delegated task cho phép dùng runtime/API/external evidence, child có thể đọc Sheet trong đúng scope đó.

## Public tools

```text
google_sheets_list_sheets(spreadsheet_id)
google_sheets_read_range(spreadsheet_id, range_name)
```

Không có tool:

```text
append
update
clear
format
delete
create
Drive search/list
```

## Security contract

Server khóa read-only ở nhiều lớp:

1. OAuth scope duy nhất:

   ```text
   https://www.googleapis.com/auth/spreadsheets.readonly
   ```

2. Chỉ nhận Google **service account** credentials.
3. `GOOGLE_SHEETS_ALLOWED_IDS` là allowlist bắt buộc; ID ngoài danh sách bị reject trước HTTP request.
4. Chỉ gọi Google Sheets API bằng HTTP `GET`; không dùng Drive API.
5. `read_range` bắt buộc explicit sheet tab + bounded A1 range, ví dụ `Orders!A1:H500`.
6. Mặc định giới hạn:

   ```text
   rows    <= 5,000
   columns <= 100
   cells   <= 50,000
   ```

7. Value rendering luôn là `FORMATTED_VALUE`; MCP không trả raw formulas.
8. Google Sheet nên share service account với quyền **Viewer**, không phải Editor.

Hai lớp read-only độc lập nên cùng tồn tại:

```text
Codex tool surface: không có mutation tool
            +
Google OAuth/API permission: spreadsheets.readonly + Viewer
```

## Google setup

### 1. Tạo service account

Trong Google Cloud project:

- enable **Google Sheets API**;
- tạo service account;
- tạo JSON key cho service account;
- lưu key ngoài Git repository.

Ví dụ:

```text
~/.config/google/agent-sheets-reader.json
```

Không commit file JSON key vào repo này hoặc repo product.

### 2. Share spreadsheet

Share Sheet cần đọc cho email service account với role **Viewer**.

Ví dụ:

```text
agent-sheets-reader@example-project.iam.gserviceaccount.com
```

### 3. Lấy spreadsheet ID

URL:

```text
https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890/edit
```

Spreadsheet ID là:

```text
1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890
```

Installer nhận **ID**, không nhận full URL.

## Install vào Codex CLI

Từ checkout của template:

```bash
cd google-sheets-template
bash scripts/google-sheets-template-check.sh
bash scripts/install-user-mcp.sh \
  --credentials ~/.config/google/agent-sheets-reader.json \
  --spreadsheet-id 1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890
```

Cho phép nhiều spreadsheet bằng cách repeat option:

```bash
bash scripts/install-user-mcp.sh \
  --credentials ~/.config/google/agent-sheets-reader.json \
  --spreadsheet-id 1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA \
  --spreadsheet-id 1BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
```

Installer:

```text
uv sync mcp/google_sheets
→ tạo ~/.local/bin/agent-google-sheets-readonly-mcp
→ persist credential path + explicit spreadsheet allowlist trong wrapper
→ codex mcp add google_sheets_readonly -- <wrapper>
→ verify registration
```

Nếu registration `google_sheets_readonly` đã tồn tại nhưng trỏ sang command khác, installer fail closed thay vì overwrite silently.

Mở fresh Codex session sau khi install để MCP được discover.

## Usage

Ví dụ prompt:

```text
Dùng Google Sheets MCP.
Đọc spreadsheet ID 1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890.
Liệt kê các tab trước, sau đó đọc Orders!A1:H500 và thống kê các order pending.
Không thay đổi dữ liệu.
```

Expected flow:

```text
google_sheets_list_sheets
→ chọn exact tab
→ google_sheets_read_range với bounded range
→ local reasoning/analysis
```

`read_range` không chấp nhận các range kiểu:

```text
A:H
Orders!A:H
Orders!A1:H
Orders!1:500
```

Thay bằng exact bounded range:

```text
Orders!A1:H500
```

Tên tab có khoảng trắng dùng A1 quoting bình thường:

```text
'Order Data'!A1:H500
```

## Runtime configuration

Stable wrapper do installer tạo export:

```text
GOOGLE_APPLICATION_CREDENTIALS
GOOGLE_SHEETS_ALLOWED_IDS
```

Server hỗ trợ optional limits:

```text
GOOGLE_SHEETS_MAX_ROWS       default 5000
GOOGLE_SHEETS_MAX_COLUMNS    default 100
GOOGLE_SHEETS_MAX_CELLS      default 50000
GOOGLE_SHEETS_TIMEOUT_SECONDS default 20
```

Muốn đổi allowlist hoặc credentials, rerun installer với full desired allowlist. Wrapper được regenerate nhưng credentials JSON không được copy vào repository.

## Verification

```bash
bash scripts/google-sheets-template-check.sh
```

Checker chạy:

```text
bash syntax checks
uv sync
unit tests
read-only server contract tests
```

Contract tests khóa các invariants chính:

- chỉ có hai MCP tools đọc;
- OAuth scope là `spreadsheets.readonly`;
- core không có POST/PUT/PATCH/DELETE;
- không dùng Google Drive scope/API;
- formatted values được force;
- allowlist reject trước network call;
- whole-column/open-ended/oversized ranges bị reject.

## Files

```text
google-sheets-template/
├── README.md
├── mcp/
│   └── google_sheets/
│       ├── core.py
│       ├── server.py
│       ├── pyproject.toml
│       └── tests/
└── scripts/
    ├── google-sheets-mcp-server.sh
    ├── google-sheets-template-check.sh
    └── install-user-mcp.sh
```

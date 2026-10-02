# user-rules-template

Nguồn của khối rule dùng chung cho agent ở cấp user: ngôn ngữ phản hồi, chất lượng câu trả lời
và truy vết code. Một nguồn duy nhất được cài vào cả Claude Code và Codex.

Template này không materialize vào workspace hay repo con, nên không cần migration.

## Cấu trúc

```text
user-rules-template/
├── README.md
├── rules/response-rules.md          nguồn của khối rule
└── scripts/install-user-rules.sh    ghi khối rule vào file instruction của user
```

## Cài đặt

```bash
user-rules-template/scripts/install-user-rules.sh
```

Script ghi `rules/response-rules.md` vào hai file:

| Client | File mặc định |
|---|---|
| Claude Code | `~/.claude/CLAUDE.md` |
| Codex | `${CODEX_HOME:-$HOME/.codex}/AGENTS.md` |

Nếu `CODEX_HOME` có giá trị, installer dùng đúng Codex home đó. Đổi file đích bằng
`--claude-file PATH` và `--codex-file PATH`. Dùng hai cờ này để thử trên bản sao trước khi ghi
vào file thật.

## Ghi đè trong phạm vi marker

Script chỉ đụng vào khối nằm giữa hai marker:

```text
<!-- AKH: response-rules -->
... nội dung từ rules/response-rules.md ...
<!-- /AKH: response-rules -->
```

| Tình huống | Hành vi |
|---|---|
| File có đúng một cặp marker | Thay nội dung giữa hai marker. Phần ngoài marker giữ nguyên |
| File chưa có marker | Thêm khối (kèm marker) lên đầu file |
| File chưa tồn tại | Tạo file chỉ chứa khối |
| File instruction là symlink hợp lệ | Giữ symlink, cập nhật file đích của symlink |
| Symlink bị gãy hoặc không trỏ tới regular file | Dừng với exit 65, không ghi target nào |
| Marker lỗi: thiếu một đầu, trùng, hoặc sai thứ tự | Dừng với exit 65, không ghi target nào |
| Nội dung đã giống nguồn | In `unchanged`, không ghi |
| Hai target trùng hoặc lồng nhau sau khi resolve path | Dừng với exit 65 trước khi tạo parent hoặc ghi file |

Installer preflight cả Claude và Codex trước khi thay file. Vì vậy lỗi marker, symlink hoặc target
lồng nhau ở một client không làm client còn lại bị cập nhật một phần.

Ghi nội dung qua file tạm rồi `os.replace`, giữ nguyên quyền của regular file cũ. Với symlink,
`os.replace` áp dụng lên file đích đã resolve, không thay bản thân symlink. Installer cũng giữ
nguyên line ending của phần nằm ngoài managed block; file CRLF không bị normalize toàn bộ sang LF.
Temporary file được đăng ký cleanup ngay sau khi tạo, kể cả khi bước ghi hoặc `copymode` thất bại.

Lần cài đầu vào file đã có sẵn nội dung tương tự nhưng chưa có marker sẽ tạo bản trùng. Xóa
nội dung cũ, hoặc bọc nó bằng marker, trước khi chạy script.

## Quy trình sửa rule

1. Sửa `rules/response-rules.md`.
2. Chạy `scripts/install-user-rules.sh`.
3. Mở session mới để agent nạp rule mới.

Không sửa trực tiếp trong khối marker ở `CLAUDE.md` hoặc `AGENTS.md`. Lần cài tiếp theo sẽ ghi đè
thay đổi đó. Rule riêng của từng client viết ngoài marker. Ví dụ mục "Ưu tiên patch tối thiểu"
nằm sau marker trong Codex `AGENTS.md`.

## Liên quan

Khối rule gọi skill `ste-vi` ở mức 80%. Skill nằm ở `writing-template/skills/ste-vi/` và cài bằng
`writing-template/scripts/install-user-skill.sh`. Cài skill trước hoặc cùng lúc với rule, nếu
không agent sẽ gặp dòng trỏ tới skill chưa tồn tại.

Codex user skill mặc định được cài vào `${CODEX_HOME:-$HOME/.codex}/skills/ste-vi`. Claude Code
user skill mặc định được cài vào `~/.claude/skills/ste-vi`.

## Kiểm tra nhanh

Thử trên bản sao, không đụng file thật:

```bash
t=$(mktemp -d)
cp ~/.claude/CLAUDE.md "$t/claude"
cp "${CODEX_HOME:-$HOME/.codex}/AGENTS.md" "$t/codex"
user-rules-template/scripts/install-user-rules.sh --claude-file "$t/claude" --codex-file "$t/codex"
```

Kết quả đúng: cả hai dòng đều in `unchanged` khi file đã được cài, hoặc `installed` khi nội dung
khác nguồn.

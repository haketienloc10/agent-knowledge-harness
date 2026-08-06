# QiQi Multi-repository Workspace Template

Thư mục này là bộ file hoàn chỉnh để đặt tại root của một local workspace chứa
nhiều Git repository độc lập.

## Thành phần

```text
AGENTS.md                         # Workflow điều phối của QiQi
identity.md                       # Danh tính, mục tiêu và giới hạn
repos.yaml                        # Registry repository machine-readable
SYSTEM_MAP.md                     # Quan hệ, contract và ownership liên repo
KNOWLEDGE.md                      # Router và vòng đời tri thức
instructions/model-routing.md     # Inventory agent/model và profile
knowledge/                        # Durable cross-repo knowledge
.qiqi/tasks/                      # Working context và lịch sử task
docs/WORKSPACE_SETUP.md           # Quy trình setup/takeover
scripts/qiqi-agent-turn.sh        # Single-flight prompt/wait theo agent
scripts/workspace-check.sh        # Kiểm tra cấu trúc và registry
```

## Ranh giới

- Workspace root giữ điều phối và tri thức cross-repo.
- Repository con giữ kiến trúc, domain rule, implementation và verification nội
  bộ.
- `.qiqi/tasks/` giữ bối cảnh làm việc, không phải nguồn tri thức chính thức.
- `knowledge/` chỉ giữ nội dung có evidence và khả năng dùng lại.
- Mỗi agent chỉ có một lifecycle owner; prompt và wait phải đi qua wrapper.

## Sử dụng

1. Sao chép toàn bộ nội dung của thư mục này vào workspace root.
2. Làm theo `docs/WORKSPACE_SETUP.md`.
3. Điền `repos.yaml`, `SYSTEM_MAP.md`, model routing và knowledge index từ bằng
   chứng thực tế.
4. Chạy:

   ```bash
   bash scripts/workspace-check.sh
   ```

5. Khởi động Herdr tại workspace root và chạy QiQi trong pane có `HERDR_ENV=1`.
6. Gửi task bằng stdin:

   ```bash
   cat <<'PROMPT' | bash scripts/qiqi-agent-turn.sh prompt <agent>
   <task prompt>
   PROMPT
   ```

Không dùng template như monorepo wrapper và không chạy Git ở workspace root để
suy luận trạng thái của các repository con.
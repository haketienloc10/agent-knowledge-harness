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
scripts/qiqi-agent-turn.sh        # Synchronous single-turn boundary
scripts/qiqi-agent-resume.sh      # Resume native session vào pane đã có
scripts/workspace-check.sh        # Kiểm tra cấu trúc và registry
```

## Ranh giới

- Workspace root giữ điều phối và tri thức cross-repo.
- Repository con giữ kiến trúc, domain rule, implementation và verification nội
  bộ.
- `.qiqi/tasks/` giữ bối cảnh làm việc, không phải nguồn tri thức chính thức.
- `knowledge/` chỉ giữ nội dung có evidence và khả năng dùng lại.
- Một phiên QiQi chỉ có một active delegated turn tại một thời điểm.
- Mọi prompt repo-agent phải đi qua `scripts/qiqi-agent-turn.sh`; wrapper không có
  `wait` mode và không dùng để polling progress.
- Resume wrapper chỉ phục hồi session; nó không tạo pane, gửi prompt hoặc chờ
  turn.

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
6. Gửi đúng một synchronous turn bằng stdin:

   ```bash
   cat <<'PROMPT' | bash scripts/qiqi-agent-turn.sh prompt <agent>
   <task prompt>
   PROMPT
   ```

   Turn trên giữ lifecycle blocked cho tới `QIQI_AGENT_TURN_FINISHED`. Nếu Codex
   hoặc tool runner tự hiển thị command dưới `Background terminals`, đó chỉ là
   transport behavior; QiQi không được tạo waiter, status check hoặc transcript
   read để theo dõi. Chỉ sau completion và reconcile mới gửi turn tiếp theo.

7. Khi tiếp tục native session đã đóng và không còn active delegated turn, tạo
   pane mới rồi chạy:

   ```bash
   bash scripts/qiqi-agent-resume.sh \
     --name <agent> \
     --pane <pane-id> \
     --kind <agent-kind> \
     -- <native-resume-arguments...>
   ```

Chỉ gửi prompt sau khi resume thành công. Không dùng template như monorepo wrapper
và không chạy Git ở workspace root để suy luận trạng thái của các repository con.

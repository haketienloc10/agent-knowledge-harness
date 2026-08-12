# Thiết lập Multi-repository Workspace cho QiQi

Tài liệu này dùng khi đưa `workspace-template/` vào một workspace thực tế. Mục
tiêu là giúp QiQi xác định đúng repository, dependency, contract, tri thức và
model mà không suy đoán.

Không bắt đầu task sản phẩm trước khi các artifact bắt buộc đã được điền hoặc
blocker đã được báo rõ.

## Kết quả Cần đạt

Sau khi hoàn thành:

- workspace root chứa các Git repository được quản lý;
- `repos.yaml` liệt kê chính xác repository và đường dẫn local;
- `SYSTEM_MAP.md` mô tả vai trò, dependency, contract và ownership liên repo;
- `identity.md` xác định QiQi là agent điều phối;
- `instructions/model-routing.md` ghi inventory agent/model đã xác nhận;
- `scripts/qiqi-agent-turn.sh` là synchronous boundary cho đúng một delegated turn;
- `scripts/qiqi-agent-resume.sh` chỉ phục hồi native session vào pane đã có;
- `KNOWLEDGE.md` và `knowledge/INDEX.md` định tuyến tri thức đúng tầng;
- `.qiqi/tasks/` sẵn sàng giữ context cho task dài hoặc cần resume;
- mọi placeholder `{{...}}` trong artifact cấu hình đã được thay;
- `bash scripts/workspace-check.sh` trả `PASS`.

## Nguyên tắc An toàn

- Bắt đầu bằng khảo sát read-only.
- Mỗi repository là Git repository độc lập.
- Không reset, clean, stash, rebase, commit, format, update dependency hoặc sửa
  source trong giai đoạn setup.
- Không tự phát minh repository, dependency, endpoint, event, command, model ID
  hoặc compatibility policy.
- Chỉ cập nhật artifact ở workspace root, trừ khi người dùng cho phép phạm vi
  khác.
- Không cài integration hoặc thay đổi config user-level khi chưa được chấp thuận.

## Bước 1: Xác nhận Workspace Root

Từ workspace root:

```bash
pwd
git rev-parse --show-toplevel 2>/dev/null || true
find . -mindepth 2 -maxdepth 2 -type d -name .git -print
```

Workspace root có thể không phải Git repository. Không biến nó thành Git repo
trừ khi người dùng yêu cầu.

Xác nhận các artifact sau tồn tại:

```text
AGENTS.md
identity.md
repos.yaml
SYSTEM_MAP.md
KNOWLEDGE.md
knowledge/INDEX.md
instructions/model-routing.md
.qiqi/tasks/TEMPLATE.md
scripts/qiqi-agent-turn.sh
scripts/qiqi-agent-resume.sh
```

## Bước 2: Lập Inventory Repository

Với từng repository dự kiến được quản lý:

```bash
git -C <repository-path> rev-parse --show-toplevel
git -C <repository-path> remote -v
git -C <repository-path> branch --show-current
git -C <repository-path> rev-parse HEAD
git -C <repository-path> status --short
```

Thu thập tên, đường dẫn, vai trò, dependency, runtime/entrypoint và command
bootstrap/verify từ code, manifest, CI hoặc tài liệu hiện hữu.

Không thêm repository chưa tồn tại local vào `repos.yaml`. Nếu workflow cần repo
chưa clone được, báo blocker thay vì điền đường dẫn giả.

## Bước 3: Điền `repos.yaml`

Mỗi entry cần:

| Trường | Yêu cầu |
|---|---|
| `name` | Tên duy nhất, ổn định và dùng thống nhất trong system map |
| `path` | Đường dẫn tương đối từ workspace root, trỏ đúng Git root |
| `role` | Vai trò thực tế của repository |
| `required_for` | Workflow hoặc capability cần repository này |
| `depends_on` | Tên repository trong registry; dùng `[]` nếu không có |

Hạ tầng như database hoặc message broker thuộc `SYSTEM_MAP.md`, không phải entry
repository giả.

## Bước 4: Điền `SYSTEM_MAP.md`

Hoàn thành bằng evidence:

1. Hình dạng hệ thống và hạ tầng dùng chung.
2. Danh sách repository khớp một-một với `repos.yaml`.
3. Thứ tự khởi động local: provider trước consumer.
4. Contract liên repository và source of truth.
5. Ownership dữ liệu và cách truy cập được phép.
6. Integration check cùng điều kiện trước khi chạy.
7. Breaking-change, deprecation và rollback policy.

Không dùng `TBD`, `TODO`, `unknown`, `N/A` hoặc đường dẫn giả để thay placeholder.
Khi chưa có thông tin, ghi blocker cụ thể và owner cần xác nhận.

## Bước 5: Khởi tạo Knowledge Index

Đọc `KNOWLEDGE.md`, sau đó điền `knowledge/INDEX.md` tối thiểu:

- glossary dùng chung nếu có;
- system flow cross-repo đã có evidence;
- contract dùng chung hiện hữu;
- decision cross-repo đang còn hiệu lực.

Không tạo tài liệu rỗng cho mọi thư mục. Không sao chép kiến trúc hoặc domain
rule nội bộ của repository con vào workspace knowledge.

Mỗi durable document phải chỉ ra scope, source of truth và evidence. Phát hiện
chưa xác minh phải nằm trong `knowledge/proposals/`.

## Bước 6: Điền Model Routing

Agent/model catalog thay đổi theo CLI, provider và account. Xác nhận từ môi
trường hiện tại:

```bash
command -v codex && codex --version
command -v claude && claude --version
herdr agent
```

Dùng model picker, provider config hoặc một phiên thử read-only để xác nhận:

- agent kind đúng theo Herdr;
- model ID chính xác;
- native arguments;
- native resume arguments chính xác cho từng agent kind cần resume;
- evidence availability;
- điểm mạnh, điểm yếu và task phù hợp;
- reasoning effort;
- concurrency/capacity của provider nếu cần lưu làm metadata vận hành.

Gán các profile `fast`, `balanced`, `deep`, `verifier`. Nhiều profile có thể dùng
cùng model. Xóa hàng mẫu không dùng.

Concurrency trong model routing chỉ là capability metadata. Nó **không** cho
phép QiQi chạy nhiều delegated turn cùng lúc; lifecycle hiện tại luôn serialize
turn theo `AGENTS.md`.

## Bước 7: Xác nhận Điều phối Phiên

Xác nhận runtime:

```bash
command -v herdr
herdr --version
command -v flock
command -v codex
codex --version
bash -n scripts/qiqi-agent-turn.sh
bash -n scripts/qiqi-agent-resume.sh
```

Để QiQi điều khiển agent, khởi động Herdr tại workspace root rồi chạy QiQi trong
pane do Herdr quản lý. Khi đó `HERDR_ENV=1` phải tồn tại.

Normal path chỉ có **một synchronous prompt turn**:

```bash
cat <<'PROMPT' | bash scripts/qiqi-agent-turn.sh prompt <agent>
<task prompt>
PROMPT
```

`qiqi-agent-turn.sh` không có `wait` mode. Không gọi `herdr agent wait` để theo
dõi một turn đang chạy.

Lệnh trên phải được hiểu là blocking cho tới khi chính invocation đó phát
`QIQI_AGENT_TURN_FINISHED`. Codex/tool runner có thể tự chuyển lệnh dài sang khu
vực `Background terminals`; việc đó **không** nhả lifecycle lock và không biến
turn thành fire-and-forget.

Trong khi invocation còn active, QiQi không được gọi thêm tool/shell/session
operation để quan sát progress, gồm:

```text
/ps
herdr agent wait|get|read
herdr pane read|process-info|wait-output
sleep/poll/status loop
```

QiQi chờ chính background terminal của invocation hiện tại phát completion.
Không tạo waiter thay thế và không dùng transport/background state để suy luận
agent đã xong.

Khi pane cũ đã đóng nhưng vẫn là cùng task, chỉ resume nếu không có active
delegated turn. Tạo pane mới tại đúng repository rồi chạy:

```bash
bash scripts/qiqi-agent-resume.sh \
  --name <agent> \
  --pane <pane-id> \
  --kind <agent-kind> \
  -- <native-resume-arguments...>
```

Chỉ gửi prompt mới sau khi resume thành công. Resume wrapper không tạo pane,
không suy đoán arguments, không gửi prompt và không dùng cho session mới.

Herdr integration là thay đổi user-level; chỉ cài khi người dùng đồng ý:

```bash
herdr integration install codex
herdr integration install claude
```

## Bước 8: Xác minh Workspace

Cần `bash`, `git`, `rg`, `flock` và `yq` phiên bản 4:

```bash
bash scripts/workspace-check.sh
```

Checker xác minh artifact bắt buộc, placeholder, turn/resume wrappers, knowledge
router và repository registry. Nó không thay thế test của repository con hoặc
kiểm tra runtime provider/model.

## Bước 9: Fresh-session Test

Mở phiên mới tại workspace root và xác nhận QiQi trả lời được:

1. Vai trò của QiQi và việc QiQi không trực tiếp làm.
2. Repository nào được quản lý và nằm ở đâu.
3. Dependency và contract quan trọng.
4. Knowledge nào cần đọc cho một task cross-repo cụ thể.
5. Model/profile nào phù hợp cho từng loại task.
6. Khi `HERDR_ENV` không bằng `1`, QiQi phải làm gì.
7. Khi task tiếp tục sau khi pane đóng, session ID nằm ở đâu và resume theo luồng
   nào.
8. Khi synchronous turn đang chạy, QiQi phải chờ marker
   `QIQI_AGENT_TURN_FINISHED` của chính invocation đó và không được tạo waiter,
   status check hay transcript read.
9. Khi Codex tự đưa turn vào `Background terminals`, QiQi phải coi lifecycle vẫn
   blocked và không gọi `/ps`, `herdr agent/pane` hay tool khác để theo dõi.

Chỉ báo workspace sẵn sàng khi checker pass, registry trỏ đúng Git root, model
được xác nhận và blocker runtime đã được phân loại.

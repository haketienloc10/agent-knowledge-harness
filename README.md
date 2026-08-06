# Agent Knowledge Harness

Bộ khung để vận hành **QiQi** tại một local workspace chứa nhiều Git repository
độc lập và tạo vòng kín tri thức giữa workspace với coding agent trong từng
repository con.

Repo này được phát triển từ các ý tưởng phù hợp trong `agent-repo-harness`,
nhưng là một sản phẩm độc lập. Nó chỉ giữ các thành phần cần cho QiQi multi-repo
và knowledge lifecycle.

## Vòng kín

```text
Đại ca
  ↓ yêu cầu và quyết định
QiQi tại workspace
  ↓ context, contract, evidence và phạm vi
Agent tại repository con
  ↓ implementation, verification và repo-local knowledge
  ↓ cross-repo knowledge candidate
QiQi
  ↓ task context hoặc knowledge proposal có evidence
Đại ca
```

## Hai template

### `workspace-template/`

Được đặt tại workspace root. Nó sở hữu QiQi, repository registry, topology,
working context, model routing, session orchestration và tri thức cross-repo.

```text
workspace-template/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── KNOWLEDGE.md
├── README.md
├── instructions/model-routing.md
├── knowledge/
├── .qiqi/tasks/
├── docs/WORKSPACE_SETUP.md
└── scripts/
    ├── qiqi-agent-turn.sh
    └── workspace-check.sh
```

### `repo-template/`

Được đặt tại Git root của từng repository con. Nó giúp coding agent hiểu kiến
trúc nội bộ, chạy verification và trả tri thức đúng tầng về QiQi.

```text
repo-template/
├── AGENTS.md
├── ARCHITECTURE.md
├── docs/
│   ├── VERIFY.md
│   └── REPO_SETUP.md
└── scripts/
    └── repo-check.sh
```

Template không tạo sẵn `docs/domain/`, `docs/specs/`, `docs/decisions/` hoặc các
artifact optional khác. Repo chỉ tạo chúng khi có nhu cầu thật.

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Repository và đường dẫn local | Workspace `repos.yaml` |
| Topology, dependency và ownership liên repo | Workspace `SYSTEM_MAP.md` |
| Luồng, contract và decision cross-repo có evidence | Workspace `knowledge/` |
| Yêu cầu, progress, blocker, session và UAT context | Workspace `.qiqi/tasks/` |
| Agent/model khả dụng và orchestration | Workspace QiQi |
| Kiến trúc, domain rule, implementation và verification nội bộ | Repository con |
| Phát hiện cross-repo chưa được QiQi duyệt | Task context hoặc `knowledge/proposals/` |

## Áp dụng vào Workspace

Nên thử trên workspace mẫu hoặc backup trước. Sao chép mà không ghi đè file hiện
có ngoài ý muốn:

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
cd /path/to/multi-repo
cat docs/WORKSPACE_SETUP.md
bash scripts/workspace-check.sh
```

Workspace checker cần `bash`, `git`, `rg`, `flock` và `yq` phiên bản 4. Nó không
chạy test của repo con.

Prompt và wait của từng agent phải đi qua `scripts/qiqi-agent-turn.sh`. Wrapper
chặn prompt rỗng, giữ một lock theo agent và chỉ kết thúc lifecycle khi phát
completion marker.

## Áp dụng vào Repository con

Với từng Git repository trong `repos.yaml`:

```bash
rsync -av --ignore-existing repo-template/ /path/to/multi-repo/<repository>/
cd /path/to/multi-repo/<repository>
cat docs/REPO_SETUP.md
bash scripts/repo-check.sh
```

Nếu repo đã có `AGENTS.md`, không ghi đè. Agent setup phải giữ workflow đặc thù
và gộp các nguyên tắc tối thiểu về Git-root boundary, architecture, verification
và knowledge output contract.

`repo-check.sh` chỉ kiểm tra cấu trúc harness và placeholder. Test hoặc build của
repo vẫn phải chạy theo `docs/VERIFY.md`.

## Thiết kế Cố ý

Repo hiện không thêm installer, vector database, embedding pipeline, knowledge
graph, watcher hoặc daemon. Markdown, Git, router, lock theo agent và evidence
được ưu tiên trước. Các lớp tự động hóa chỉ nên bổ sung sau khi vòng kín thu
thập, xác minh, chắt lọc và định tuyến đã ổn định.
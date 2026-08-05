# Agent Knowledge Harness

Bộ khung hoàn chỉnh để vận hành **QiQi** tại một local workspace chứa nhiều Git
repository độc lập, đồng thời quản lý tri thức cross-repo có evidence.

Repo này được phát triển từ các ý tưởng workspace orchestration trong
`agent-repo-harness`, nhưng là một sản phẩm độc lập. Nó chỉ lấy và điều chỉnh các
thành phần cần cho multi-repo QiQi; không sao chép workflow dành cho single repo
hoặc toàn bộ harness cũ.

## Mục tiêu

- Cung cấp QiQi hoàn chỉnh tại workspace root.
- Định tuyến yêu cầu đến đúng repository và đúng coding agent.
- Giữ context cho task dài, task cần resume hoặc UAT lại.
- Chuyển decision, contract và evidence giữa các phiên phụ thuộc.
- Tách foundation, durable knowledge và working context.
- Giữ chi tiết nội bộ tại repository sở hữu thay vì gom mọi thứ vào workspace.

## Cấu trúc

```text
workspace-template/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── KNOWLEDGE.md
├── README.md
├── instructions/
│   └── model-routing.md
├── knowledge/
│   ├── INDEX.md
│   ├── glossary.md
│   ├── systems/
│   ├── contracts/
│   ├── decisions/
│   └── proposals/
├── .qiqi/
│   └── tasks/
│       ├── TEMPLATE.md
│       ├── active/
│       └── completed/
├── .agents/
│   └── skills/
│       └── herdr/
│           ├── SKILL.md
│           ├── LICENSE.txt
│           └── SOURCE.md
├── docs/
│   └── WORKSPACE_SETUP.md
└── scripts/
    └── workspace-check.sh
```

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Repository và đường dẫn local | `repos.yaml` |
| Topology, dependency và ownership liên repo | `SYSTEM_MAP.md` |
| Luồng, contract và decision cross-repo có evidence | `knowledge/` |
| Kiến trúc, domain rule và verification nội bộ | Tài liệu trong repo con |
| Yêu cầu, progress, blocker, session và UAT context | `.qiqi/tasks/` |
| Agent/model khả dụng | `instructions/model-routing.md` |
| Workflow điều phối | `AGENTS.md` và `identity.md` |

## Áp dụng vào Workspace

Nên thử trên một workspace mẫu hoặc backup trước. Sao chép nội dung template vào
workspace root mà không ghi đè file hiện có ngoài ý muốn, ví dụ với `rsync`:

```bash
rsync -av --ignore-existing workspace-template/ /path/to/multi-repo/
```

Sau đó:

```bash
cd /path/to/multi-repo
cat docs/WORKSPACE_SETUP.md
bash scripts/workspace-check.sh
```

Checker cần `bash`, `git`, `rg` và `yq` phiên bản 4. Nó xác minh cấu trúc,
placeholder, Herdr bundle và repository registry; không chạy test của repo con.

## Thiết kế Cố ý

Repo hiện không thêm vector database, embedding pipeline, knowledge graph hoặc
service runtime. Markdown, Git, router và evidence được ưu tiên trước. Các lớp
tìm kiếm nâng cao chỉ nên bổ sung khi workflow thu thập và chắt lọc tri thức đã
ổn định.

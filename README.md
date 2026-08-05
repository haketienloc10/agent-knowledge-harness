# Agent Knowledge Harness

Bộ khung Markdown tối giản để agent sử dụng tri thức đúng phạm vi trong một
workspace chứa nhiều Git repository độc lập.

Repo này **không thay thế** `agent-repo-harness`. `agent-repo-harness` quản lý
vai trò QiQi, registry repository, system map, model routing và vòng đời phiên.
Repo này chỉ bổ sung lớp tri thức dùng chung cho workspace.

## Mục tiêu

- Định tuyến agent đến đúng tài liệu thay vì đọc toàn bộ workspace.
- Tách tri thức nền tảng, tri thức lâu bền và bối cảnh công việc.
- Yêu cầu evidence cho các kết luận được xem là đã xác nhận.
- Cho agent đề xuất tri thức trước khi cập nhật nguồn chính thức.
- Giữ tri thức nội bộ của từng repository tại chính repository đó.

## Ranh giới sở hữu

| Loại thông tin | Nơi lưu |
|---|---|
| Quan hệ liên repository, contract dùng chung, quyết định cross-repo | `knowledge/` tại workspace root |
| Kiến trúc, domain rule, verification và quyết định nội bộ | Tài liệu trong repository con |
| Yêu cầu, tiến độ, blocker và kết quả tạm thời của task | `.qiqi/tasks/` |
| Template, quy tắc và cấu trúc có thể tái sử dụng | Repo này |

## Cấu trúc template

```text
workspace-template/
├── KNOWLEDGE.md
├── integration/
│   └── AGENTS.md.fragment
├── knowledge/
│   ├── INDEX.md
│   ├── glossary.md
│   ├── systems/
│   ├── contracts/
│   ├── decisions/
│   └── proposals/
└── .qiqi/
    └── tasks/
        ├── TEMPLATE.md
        ├── active/
        └── completed/
```

## Cách áp dụng

1. Sao chép `workspace-template/KNOWLEDGE.md` và `workspace-template/knowledge/`
   vào workspace root.
2. Chỉ sao chép `.qiqi/tasks/` khi workspace chưa có cấu trúc task tương đương.
3. Gộp nội dung `integration/AGENTS.md.fragment` vào `AGENTS.md` hiện có; không
   thay thế toàn bộ file điều phối QiQi.
4. Điền `knowledge/INDEX.md`, sau đó chỉ tạo tài liệu khi có tri thức thật sự cần
   dùng lại.

Template cố ý không chứa installer, vector database, embedding pipeline hoặc
knowledge graph. Các thành phần đó chỉ nên được thêm sau khi workflow thu thập,
xác minh, chắt lọc và định tuyến đã ổn định.

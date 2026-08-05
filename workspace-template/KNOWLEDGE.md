# KNOWLEDGE.md — Định tuyến tri thức tại workspace

File này định nghĩa cách QiQi và agent sử dụng tri thức tại workspace chứa nhiều
Git repository độc lập. Nó không thay thế `AGENTS.md`, `SYSTEM_MAP.md`,
`repos.yaml` hoặc tài liệu của repository con.

## Ba tầng tri thức

### 1. Foundation

Nguồn giúp agent hiểu workspace nhưng ít thay đổi:

- `repos.yaml`: repository nào tồn tại và nằm ở đâu;
- `SYSTEM_MAP.md`: quan hệ liên repository;
- `knowledge/glossary.md`: thuật ngữ dùng chung.

### 2. Durable knowledge

Tri thức đã được xác minh và có thể dùng lại:

- `knowledge/systems/`: hành vi hoặc luồng cross-repo;
- `knowledge/contracts/`: API, event, schema và dữ liệu trao đổi;
- `knowledge/decisions/`: quyết định ảnh hưởng nhiều repository.

### 3. Working context

Bối cảnh đang thay đổi trong quá trình thực hiện:

- `.qiqi/tasks/active/`: yêu cầu, tiến độ, blocker, session và kết quả tạm thời;
- `.qiqi/tasks/completed/`: lịch sử task đã kết thúc.

Task document không mặc nhiên là durable knowledge.

## Quy tắc định tuyến

| Câu hỏi hoặc thay đổi | Nguồn cần đọc |
|---|---|
| Repo nào sở hữu chức năng | `repos.yaml` |
| Luồng đi qua nhiều repo | `SYSTEM_MAP.md`, sau đó `knowledge/systems/` |
| Field/API/event dùng giữa các repo | `knowledge/contracts/` |
| Lý do đã chọn một hướng cross-repo | `knowledge/decisions/` |
| Chi tiết code, kiến trúc hoặc domain của một repo | Tài liệu trong repo đó |
| Trạng thái công việc hiện tại | `.qiqi/tasks/active/` |

Không đọc toàn bộ `knowledge/`. Bắt đầu từ `knowledge/INDEX.md`, chọn tài liệu có
scope phù hợp rồi chỉ mở các nguồn được liên kết.

## Evidence

Một kết luận chỉ được ghi là đã xác nhận khi chỉ ra được nguồn kiểm chứng, ví dụ:

- đường dẫn code hoặc cấu hình;
- test hoặc command verification;
- contract/spec chính thức;
- issue, ticket hoặc quyết định đã được chấp thuận;
- output runtime có thể tái kiểm tra.

Nếu chưa đủ evidence, ghi rõ `status: proposed` hoặc `status: unverified`. Không
biến suy luận của agent thành sự thật bằng cách viết theo giọng khẳng định.

## Vòng đời tri thức

```text
Phát hiện trong task
        ↓
Tạo proposal có evidence
        ↓
Xác minh scope và source of truth
        ↓
Chuyển nội dung đã chắt lọc vào systems/contracts/decisions
        ↓
Cập nhật knowledge/INDEX.md
```

Agent không cập nhật durable knowledge chỉ vì task đã hoàn thành. Chỉ cập nhật
khi nội dung có khả năng được dùng lại và không thuộc tài liệu nội bộ của một
repository con.

## Tránh trùng lặp

- Workspace chỉ giữ góc nhìn cross-repo; chi tiết triển khai thuộc repo con.
- Contract document liên kết đến source chính thức thay vì sao chép toàn bộ.
- Task completed giữ lịch sử nhưng không cạnh tranh với durable knowledge.
- Khi hai tài liệu cùng mô tả một sự thật, phải chọn một source of truth và đổi
  tài liệu còn lại thành liên kết hoặc bản tóm tắt có phạm vi rõ.

## Giao context cho agent con

QiQi chỉ truyền phần tri thức liên quan trực tiếp đến task:

- mục tiêu và phạm vi;
- quyết định đã chốt;
- contract hoặc dependency cần tuân thủ;
- đường dẫn đến source of truth;
- phần chưa chắc chắn cần điều tra.

Không gửi toàn bộ thư viện tri thức vào prompt và không yêu cầu agent con điều
tra lại kết luận đã có evidence, trừ khi xuất hiện bằng chứng mâu thuẫn mới.

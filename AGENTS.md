# AGENTS.md

Repo này phát triển hai bộ khung phối hợp với nhau trong multi-repository
workspace:

- `workspace-template/`: QiQi orchestration, task continuity và cross-repo
  knowledge management;
- `repo-template/`: workflow tối thiểu cho coding agent trong từng repository
  con, gồm architecture, verification và knowledge output contract.

Repo này không chứa tri thức nghiệp vụ thật của một workspace hoặc repository cụ
thể.

## Nguyên tắc

- Giữ QiQi là agent điều phối; không biến QiQi thành coding agent của repo con.
- Mỗi repository con sở hữu workflow, kiến trúc, domain rule, implementation và
  verification nội bộ.
- Workspace sở hữu registry, topology, context điều phối và tri thức cross-repo.
- Agent repo con không sửa workspace knowledge; nó chỉ trả candidate có evidence
  cho QiQi xử lý.
- Mỗi agent chỉ có một lifecycle owner; prompt và wait phải đi qua wrapper có
  lock theo agent.
- Ưu tiên Markdown có thể đọc trực tiếp, source of truth rõ và evidence có thể
  kiểm tra.
- Không thêm vector database, embedding, service runtime hoặc dependency ngoài
  khi chưa có nhu cầu đã được chứng minh.
- Ví dụ trong template phải trung lập, không chứa dữ liệu thật của dự án.

## Khi thay đổi Workspace Template

1. Kiểm tra quy tắc mới có chồng chéo với `AGENTS.md`, `KNOWLEDGE.md`,
   `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc tài liệu repo con hay không.
2. Ưu tiên sửa router và ownership trước khi thêm loại artifact mới.
3. Bảo đảm prompt QiQi truyền đủ context nhưng không sao chép toàn bộ knowledge.
4. Giữ proposal là vùng chờ; durable knowledge cần evidence và scope rõ.
5. Giữ task document là working context, không phải source of truth mặc định.
6. Giữ `scripts/qiqi-agent-turn.sh` là đường duy nhất cho prompt và wait; không
   tạo thêm waiter, watcher hoặc daemon song song.
7. Nếu thay đổi file bắt buộc, cập nhật đồng thời setup guide, checker và README
   liên quan.

## Khi thay đổi Repository Template

1. Giữ template tối thiểu và không tạo sẵn artifact optional rỗng.
2. Không đưa identity, model routing, session orchestration, workspace task hoặc
   cross-repo knowledge store xuống repo con.
3. Bảo vệ Git-root boundary và cấm agent tự sửa repository anh em.
4. Repo-local knowledge phải cập nhật tại source of truth của repo sở hữu.
5. Cross-repo knowledge phải được trả về QiQi dưới dạng candidate; không promote
   trực tiếp từ agent repo con.
6. Output contract giữa agent con và QiQi phải đồng bộ ở cả
   `repo-template/AGENTS.md` và `workspace-template/AGENTS.md`.

## Kiểm tra

Review tối thiểu phải xác nhận:

- mỗi template tự chứa các file mà `AGENTS.md` của nó định tuyến tới;
- checker chỉ kiểm tra harness, không chạy test hoặc sửa source sản phẩm;
- lifecycle wrapper chặn prompt rỗng, giữ lock theo agent và phát completion
  marker;
- ranh giới workspace knowledge và repo-local knowledge không bị phá vỡ;
- candidate chưa xác minh không được truyền hoặc lưu như sự thật;
- README phản ánh đúng cách cài cả workspace và repo con.

Không sao chép thêm thành phần từ `agent-repo-harness` nếu không phục vụ trực
tiếp vòng kín QiQi multi-repo hoặc knowledge lifecycle.
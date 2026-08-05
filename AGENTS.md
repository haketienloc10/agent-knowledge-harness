# AGENTS.md

Repo này phát triển bộ khung hoàn chỉnh cho **QiQi** tại multi-repository
workspace, gồm orchestration, task continuity và knowledge management.

`workspace-template/` là sản phẩm được cài vào workspace đích. Repo này không
chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- Giữ QiQi là agent điều phối; không biến QiQi thành coding agent của repo con.
- Mỗi repository con vẫn sở hữu workflow, kiến trúc, domain rule và verification
  nội bộ.
- Workspace chỉ sở hữu registry, topology, context điều phối và tri thức
  cross-repo.
- Ưu tiên Markdown có thể đọc trực tiếp, source of truth rõ và evidence có thể
  kiểm tra.
- Không thêm vector database, embedding, service runtime hoặc dependency ngoài
  khi chưa có nhu cầu đã được chứng minh.
- Ví dụ trong template phải trung lập, không chứa dữ liệu thật của dự án.

## Khi thay đổi Template

1. Kiểm tra quy tắc mới có chồng chéo với `AGENTS.md`, `KNOWLEDGE.md`,
   `SYSTEM_MAP.md`, `.qiqi/tasks/` hoặc tài liệu repo con hay không.
2. Ưu tiên sửa router và ownership trước khi thêm loại artifact mới.
3. Bảo đảm prompt QiQi truyền đủ context nhưng không sao chép toàn bộ knowledge.
4. Giữ proposal là vùng chờ; durable knowledge cần evidence và scope rõ.
5. Giữ task document là working context, không phải source of truth mặc định.
6. Nếu thay đổi file bắt buộc, cập nhật đồng thời:
   - `workspace-template/README.md`;
   - `workspace-template/docs/WORKSPACE_SETUP.md`;
   - `workspace-template/scripts/workspace-check.sh`;
   - README ở repo root.
7. Không sao chép thêm thành phần từ `agent-repo-harness` nếu không phục vụ trực
   tiếp QiQi multi-repo hoặc knowledge lifecycle.

## Kiểm tra

Review tối thiểu phải xác nhận:

- template tự chứa các file mà `AGENTS.md` định tuyến tới;
- không còn fragment cần gộp thủ công;
- Herdr skill có license và provenance;
- checker không chạy test hoặc sửa repository con;
- ranh giới workspace knowledge và repo-local knowledge không bị phá vỡ.

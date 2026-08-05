# AGENTS.md

Repo này phát triển bộ khung tri thức dùng chung cho agent trong multi-repository
workspace. Nó không chứa tri thức nghiệp vụ thật của một workspace cụ thể.

## Nguyên tắc

- Giữ template tối giản và ưu tiên Markdown có thể đọc trực tiếp.
- Không sao chép toàn bộ workflow từ `agent-repo-harness`.
- Không tạo nguồn sự thật thứ hai cho thông tin đã thuộc `SYSTEM_MAP.md`,
  `repos.yaml` hoặc tài liệu của repository con.
- Mọi quy tắc mới phải xác định rõ phạm vi sở hữu và cách agent tìm đến nó.
- Không thêm vector database, embedding, service runtime hoặc dependency bên
  ngoài khi chưa có yêu cầu rõ.
- Ví dụ trong template phải trung lập, không chứa dữ liệu thật của dự án.

## Khi thay đổi template

1. Kiểm tra thay đổi có trùng trách nhiệm với workspace harness hoặc repo con
   hay không.
2. Ưu tiên sửa file định tuyến trước khi thêm loại tài liệu mới.
3. Giữ proposal là vùng chờ; tri thức chỉ trở thành durable khi có evidence.
4. Bảo đảm task document không bị coi là nguồn tri thức chính thức.
5. Cập nhật `README.md` khi cấu trúc hoặc ranh giới sở hữu thay đổi.

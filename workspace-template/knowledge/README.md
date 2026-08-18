# Workspace Knowledge

Thư mục này lưu tri thức **cross-repo có khả năng dùng lại** cho nhiều task trong
workspace. Chi tiết implementation, architecture, domain rule hoặc verification chỉ
thuộc một repository phải ở source of truth của repository đó, không sao chép lên
workspace.

QiQi là agent đọc và cập nhật workspace knowledge. Execution agent không tự đọc thư mục này. QiQi chắt lọc phần context liên quan và truyền trực tiếp trong task prompt.

## Cách đọc

1. Bắt đầu từ `INDEX.md`.
2. Dựa vào `Summary`, `Khi nào cần đọc` và `Phạm vi` để chọn exact document.
3. Chỉ mở document liên quan đến task hiện tại; không quét toàn bộ `knowledge/`.
4. Dùng knowledge như workspace context để lập kế hoạch hoặc viết self-contained
   task prompt cho execution agent.

`INDEX.md` là mục lục tìm kiếm, không phải nơi chứa toàn bộ nội dung knowledge.

## Khi nào cần lưu

Chỉ tạo hoặc cập nhật workspace knowledge khi thông tin:

- ảnh hưởng từ hai repository trở lên hoặc một boundary dùng chung;
- đã có evidence đủ để dùng làm context;
- có khả năng được dùng lại ở task tương lai.

Không cần lưu durable knowledge khi thông tin chỉ phục vụ handoff của task hiện tại.
Trong trường hợp đó, QiQi đọc result của producer rồi truyền fact/evidence cần thiết
thẳng vào prompt của consumer.

## Nơi lưu

- `systems/`: luồng hoặc behavior cần góc nhìn từ nhiều repository.
- `contracts/`: API, event, schema, file format hoặc field producer/consumer cùng
  phụ thuộc.
- `decisions/`: quyết định ảnh hưởng nhiều repository hoặc thay đổi ownership.
- `glossary.md`: thuật ngữ dùng chung trong workspace.
- `SYSTEM_MAP.md` ở workspace root: topology, ownership và dependency tổng thể;
  cập nhật file này thay vì tạo knowledge document khi thay đổi chủ yếu là bản đồ hệ
  thống.

Dùng format của `README.md` trong từng thư mục khi tạo document mới.

## Cách cập nhật từ result artifact

Sau khi execution agent trả terminal result, QiQi đọc `### Cross-repo Impact`.

- Nếu impact cần cho downstream task hiện tại: truyền fact/evidence liên quan vào
  downstream task prompt.
- Nếu impact có khả năng dùng lại: tạo/cập nhật đúng workspace knowledge document.
- Nếu impact chỉ là chi tiết repo-local: giữ ở repo-local source of truth, không copy.
- Nếu impact không còn giá trị sau task hiện tại: không tạo document chỉ để lưu lịch
  sử; result artifact đã giữ terminal handoff.

## Nội dung tối thiểu của knowledge document

Document nên đủ ngắn để đọc theo nhu cầu và nêu được:

- summary hoặc kết luận cần dùng lại;
- phạm vi/repository liên quan;
- contract, flow hoặc decision cần giữ;
- evidence/source of truth có thể kiểm tra;
- link tới repo-local source khi cần, thay vì sao chép implementation detail.

## Cập nhật INDEX.md

Mỗi khi tạo, đổi phạm vi hoặc xóa một durable knowledge document, cập nhật
`INDEX.md` trong cùng thay đổi.

Mỗi dòng index cần giúp QiQi quyết định **có cần đọc document đó cho task hiện tại
hay không**. Ít nhất phải có:

- `Tài liệu`;
- `Summary`;
- `Khi nào cần đọc`;
- `Phạm vi`.

Không đưa `.qiqi/tasks/`, `.qiqi/runs/` hoặc repo-local docs vào index. Những
artifact đó có lifecycle và ownership riêng.

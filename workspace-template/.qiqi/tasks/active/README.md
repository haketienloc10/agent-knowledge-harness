# Active Tasks

Mọi **task thực thi** tại workspace phải có một file trong thư mục này, trừ các
trường hợp stateless được nêu dưới đây. Quy tắc này vẫn áp dụng cho task chỉ chạm
một repository, hoàn thành trong một lượt hoặc không có dependency.

Task thực thi gồm investigation, implementation, verification, thay đổi
workspace/repository, delegation hoặc công việc operational khác mà QiQi phải thực
hiện thay vì chỉ trả lời hội thoại.

Không cần task file cho:

- hỏi đáp, giải thích hoặc clarification thông thường khi QiQi chỉ cần trả lời;
- tổng hợp, biên tập hoặc lưu workspace document từ result/evidence đã có, khi
  không cần delegation mới hoặc continuation state.

Nếu update tài liệu phát sinh từ một active task, giữ nó trong task hiện tại thay
vì tạo task mới chỉ cho bước tổng hợp hoặc persist.

Nếu công việc cần investigation, implementation, verification, delegation hoặc
phát sinh state phải tiếp tục qua lượt khác, tạo active task trước phần thực thi đó.

Tạo file mới từ `../TEMPLATE.md` trước khi bắt đầu task. Nếu task hoàn thành trong
cùng lượt, vẫn tạo ở `active/`, reconcile kết quả rồi chuyển sang `completed/`.

Chỉ cập nhật state có giá trị cho task: scope, decision, dependency, terminal
milestone/outcome, verification, native `session_id`, `result_path`, blocker và
handoff cần tiếp tục. Không ghi working transcript, live child state hoặc progress
polling.

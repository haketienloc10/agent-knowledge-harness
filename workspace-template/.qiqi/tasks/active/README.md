# Active Tasks

Mọi **task thực thi** tại workspace phải có một file trong thư mục này, kể cả task
chỉ chạm một repository, hoàn thành trong một lượt hoặc không có dependency.

Task thực thi gồm investigation, implementation, verification, thay đổi
workspace/repository, delegation hoặc công việc operational khác mà QiQi phải thực
hiện thay vì chỉ trả lời hội thoại.

Chỉ bỏ qua task file cho hỏi đáp, giải thích hoặc clarification thông thường khi
QiQi chỉ cần trả lời và không bắt đầu công việc thực thi. Nếu yêu cầu chuyển từ hỏi
đáp sang thực hiện công việc, tạo task file trước khi bắt đầu phần thực thi.

Tạo file mới từ `../TEMPLATE.md` trước khi bắt đầu task. Nếu task hoàn thành trong
cùng lượt, vẫn tạo ở `active/`, reconcile kết quả rồi chuyển sang `completed/`.

Chỉ cập nhật state có giá trị cho task: scope, decision, dependency, terminal
milestone/outcome, verification, native `session_id`, `result_path`, blocker và
handoff cần tiếp tục. Không ghi working transcript, live child state hoặc progress
polling.

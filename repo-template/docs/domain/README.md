# Domain Knowledge

Thư mục này lưu thuật ngữ nghiệp vụ, entity lifecycle, state semantics và
invariant thuộc riêng repository hiện tại.

Không cần tạo tài liệu cho thông tin có thể đọc thấy trực tiếp và rõ ràng từ
source, test hoặc tài liệu hiện có. Khi task xác nhận domain knowledge không tầm
thường và có khả năng hữu ích cho task tương lai, tạo hoặc cập nhật tài liệu phù
hợp để giữ kết luận đã được evidence xác nhận.

Mỗi tài liệu nên nêu rõ:

- phạm vi và thuật ngữ liên quan;
- rule hoặc invariant cần được bảo toàn;
- trạng thái, transition hoặc lifecycle nếu có;
- evidence từ source, test hoặc behavior đã xác minh.

Không dùng thư mục này cho contract cross-repo, quyết định kiến trúc hoặc log
điều tra.

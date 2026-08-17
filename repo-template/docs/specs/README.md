# Repository Specifications

Thư mục này lưu behavior, contract và acceptance criteria do repository hiện
tại sở hữu và cần được bảo toàn qua thay đổi.

Không cần tạo tài liệu cho behavior có thể đọc thấy trực tiếp và rõ ràng từ source
hoặc test hiện tại. Khi task xác nhận behavior/contract không tầm thường mà agent
tương lai cần hiểu ổn định hoặc nhiều thay đổi có thể dùng lại, tạo hoặc cập nhật
specification phù hợp.

Mỗi tài liệu nên nêu rõ:

- mục đích và phạm vi;
- behavior hoặc contract bắt buộc;
- input, output, failure và fallback liên quan;
- acceptance criteria;
- verification và source of truth.

Nếu contract ảnh hưởng nhiều repository, giữ source of truth repo-local đúng phạm
vi của repo hiện tại và handoff phần ảnh hưởng cùng evidence cho QiQi qua
Cross-repo Impact. Không mô tả repository khác như nguồn sự thật tại đây.

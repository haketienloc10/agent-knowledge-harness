# Repository Specifications

Thư mục này lưu behavior, contract và acceptance criteria do repository hiện
tại sở hữu và cần được bảo toàn qua thay đổi.

Chỉ tạo tài liệu khi source và test chưa đủ để agent hiểu ổn định hành vi cần
giữ hoặc khi nhiều thay đổi tiếp theo cần cùng một specification.

Mỗi tài liệu nên nêu rõ:

- mục đích và phạm vi;
- behavior hoặc contract bắt buộc;
- input, output, failure và fallback liên quan;
- acceptance criteria;
- verification và source of truth.

Nếu contract ảnh hưởng nhiều repository, giữ source of truth repo-local đúng phạm
vi của repo hiện tại và handoff phần ảnh hưởng cùng evidence cho QiQi qua
Cross-repo Impact. Không mô tả repository khác như nguồn sự thật tại đây.

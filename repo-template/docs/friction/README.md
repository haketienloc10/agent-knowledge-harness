# Friction Observations

Thư mục này lưu các vấn đề đã quan sát được khiến agent đổi planned approach,
thực hiện lại một bước có chi phí hoặc làm giảm độ tin cậy của feedback loop.

Khi cần ghi nhận, chỉ đọc file README này. Không đọc, tìm kiếm, tổng hợp, gộp
hoặc cập nhật các friction observation đã có.

Mỗi friction là một file riêng:

`<yyyy-mm-dd>-<short-name>.md`

Format:

```md
# <Mô tả cụ thể vấn đề>

- Impact:
- Evidence:
```

Chỉ tạo file khi friction đáng kể, thuộc repository, tooling hoặc instruction
của task và có evidence kiểm tra lại được. Không bắt buộc tìm root cause, đề
xuất giải pháp hoặc sửa friction trong task hiện tại.

Không ghi typo, command lỗi không đáng kể, hậu quả suy đoán, bug sản phẩm đang
được xử lý hoặc việc agent thiếu kiến thức chung. Friction thuộc workspace hoặc
cơ chế điều phối phải được trả về QiQi, không ghi tại đây.

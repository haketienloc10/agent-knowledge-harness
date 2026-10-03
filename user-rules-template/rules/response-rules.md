## Communication defaults

- Always reply in Vietnamese by default.
- Keep technical terms, code, commands, file paths, config keys, and error messages in their original form unless translation is explicitly requested.
- If the user writes in another language and explicitly asks for that language, follow the user's language for that response.
- Prefer concise, operational Vietnamese.
- Do not switch to English unless the user asks, the content is a verbatim quote, or keeping the original wording is technically important.

## Ngôn ngữ tài liệu repository

- Khi tạo hoặc cập nhật Markdown, plan, spec hoặc nội dung hướng tới người đọc trong repository, dùng tiếng Việt mặc định nếu không có yêu cầu ngôn ngữ khác.
- Chỉ giữ tiếng Anh cho code, comment code, java docs, identifier, API field, command, path, log/error message và thuật ngữ kỹ thuật cần giữ nguyên.
- Không suy diễn rằng ticket hoặc source code tiếng Anh là yêu cầu viết tài liệu tiếng Anh.

## Chất lượng câu trả lời

Tránh câu trả lời trừu tượng.

Khi giải thích quyết định, kế hoạch, rủi ro, bug, kiến trúc, trade-off hoặc thay đổi code, dùng ví dụ cụ thể và lập luận nhân quả theo từng bước. Với code, ưu tiên giải thích theo execution flow để người đọc có thể tự truy vết implementation.

Cấu trúc đầy đủ bên dưới chỉ dùng khi giải thích bug, kiến trúc, quyết định hoặc thay đổi code từ vài file trở lên. Việc nhỏ thì trả lời ngắn: nêu kết quả và cách kiểm chứng.

Khi viết hoặc sửa tài liệu tiếng Việt hướng tới người đọc, hoặc khi câu trả lời cần giải thích kỹ thuật từ vài câu trở lên, dùng skill `ste-vi` ở mức 80%.

Không cần kích hoạt `ste-vi` cho câu trả lời ngắn, xác nhận, output thuần dữ liệu, code, command, log hoặc error message.

Với giải thích khái niệm, quyết định hoặc trade-off, ưu tiên cấu trúc sau:

1. Điều gì xảy ra
2. Vì sao điều đó xảy ra
3. Ví dụ cụ thể
4. Tác động dẫn đến
5. Hành động được khuyến nghị

## Chọn hình thức giải thích

Bắt đầu bằng văn bản.

Không kéo dài prose nếu độ khó nằm ở quan hệ, thứ tự hoặc behavior của hệ thống. Chuyển sang sơ đồ khi một trong các điều kiện sau đúng:

- từ 3 component trở lên tương tác;
- có từ 2 nhánh logic trở lên;
- có lifecycle hoặc state transition;
- hiểu đúng phụ thuộc vào message order hoặc execution order;
- cùng các entity được mô tả lặp lại bằng quan hệ gọi/phụ thuộc;
- prose cần khoảng hơn 8 câu chỉ để mô tả structure.

Chọn sơ đồ theo loại vấn đề:

- flowchart: procedure hoặc branching logic;
- sequence diagram: API call, service interaction, request lifecycle;
- state diagram: state transition hoặc workflow state;
- architecture diagram: component, dependency, infrastructure;
- timeline: event, incident, migration;
- table: so sánh thay vì quan hệ.

Cân nhắc interactive HTML khi sơ đồ tĩnh không đủ và người đọc cần thao tác với input hoặc state, ví dụ thay đổi tham số, bật/tắt failure, lọc timeline hoặc khám phá dependency.

Ưu tiên:

`text -> diagram -> interactive`

thay vì:

`short text -> long text -> very long text`

Không tạo HTML tương tác chỉ để trang trí.

## Khả năng truy vết code từ câu trả lời

Khi câu trả lời liên quan đến việc đọc, phân tích, sửa hoặc review code, phải giúp người đọc có thể lần ngược lại implementation để tự kiểm chứng. Với các câu trả lời này, dùng cấu trúc bên dưới thay cho cấu trúc 5 mục ở mục "Chất lượng câu trả lời". Ngưỡng "việc nhỏ" ở mục đó vẫn áp dụng.

Ưu tiên mô tả theo execution flow thực tế của code:

1. **Điểm bắt đầu**
   - Chỉ rõ entry point của chức năng: route, command, handler, component, public method, event hoặc API tương ứng.
   - Nêu `file path` và symbol/function/class liên quan.

2. **Luồng xử lý chính**
   - Theo thứ tự execution, chỉ ra code đi từ đâu tới đâu.
   - Với mỗi bước quan trọng, nêu:
     - `file path`
     - function/class/method
     - vai trò của đoạn code đó
     - điều kiện nào khiến flow đi sang bước tiếp theo

3. **Điểm thay đổi**
   - Chỉ rõ logic được sửa nằm ở đâu trong flow.
   - Giải thích behavior trước khi sửa và sau khi sửa.
   - Nếu có nhiều file thay đổi, giải thích quan hệ giữa các thay đổi thay vì chỉ liệt kê file.

4. **Điểm kết thúc và side effect**
   - Chỉ ra kết quả cuối cùng được trả về, persist, render, emit hoặc gửi ra ngoài ở đâu.
   - Nêu side effect quan trọng nếu có, ví dụ database write, state update, API call, event hoặc cache mutation.

5. **Cách kiểm chứng**
   - Chỉ ra test liên quan hoặc command đã dùng để verify.
   - Khi phù hợp, đưa ra một đường kiểm tra ngắn để người đọc có thể tự mở code và xác nhận lại implementation.

Không chỉ nói "đã sửa X để xử lý Y". Câu trả lời phải đủ thông tin để người đọc có thể đi theo:

`entry point -> logic chính -> điểm thay đổi -> output/side effect -> verification`

Ví dụ, thay vì:

"Đã sửa validation trong user service."

Ưu tiên:

"`POST /users` đi vào `src/routes/users.ts:createUser`, sau đó gọi
`src/services/user-service.ts:createUser`. Validation email nằm ở
`validateCreateUser()` trước bước `repository.insert()`. Thay đổi nằm tại đây:
email trùng trước đây đi tiếp tới database và phụ thuộc unique constraint;
sau thay đổi, service trả `ConflictError` trước khi insert. Kết quả được map
thành HTTP 409 tại `src/http/error-handler.ts`. Có thể kiểm chứng bằng
`tests/users/create-user.test.ts` với case duplicate email."

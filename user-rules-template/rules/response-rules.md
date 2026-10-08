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

Khi phân tích code, phải giúp người đọc truy ngược từ kết quả quan sát được đến nguồn tạo ra kết quả đó. Ưu tiên **cây phụ thuộc giá trị và điều kiện** như ví dụ bên dưới, thay vì mặc định liệt kê tuần tự các file hoặc dùng cấu trúc 5 mục. Với thay đổi code, bug liên quan thứ tự thực thi hoặc side effect, bổ sung execution flow khi cần. Việc nhỏ chỉ cần nêu kết quả và nơi kiểm chứng.

### Cách trình bày

- **Bắt đầu từ kết quả cần giải thích:** UI field, API response, persisted value, state hoặc behavior. Nếu có UI, nêu màn hình, tab và trường liên quan.
- **Truy ngược nguồn của từng giá trị:** ghi công thức ngay tại node cha; thụt vào bên dưới các operand và nguồn tạo ra chúng. Dùng `→` cho quan hệ phụ thuộc. Không thay cây nguồn gốc bằng danh sách file.
- **Gắn module vào tên giá trị:** ưu tiên dạng `module.field` hoặc `module.object.field` (ví dụ `corgi.line[i].ticketFare`, `searchAir.line[i].ticketTax`, `gw.fareForOnePerson`). Giải thích ngắn quy ước module và index nếu cần.
- **Tách các nhánh có điều kiện:** đặt `when <điều kiện>` hoặc `otherwise` ngay dưới phép tính hoặc nhánh tương ứng. Giữ nguyên toán tử, độ ưu tiên và trường hợp biên. Không gộp các nhánh có công thức khác nhau.
- **Phân biệt đọc và tính toán:** nếu module chỉ map/copy/read một field thì ghi rõ "chỉ đọc", rồi truy tiếp đến nơi thực sự tính giá trị. Không gán phép tính cho module trung gian.
- **Chỉ ra bằng chứng tại node:** ghi `path/to/File.ext:line` hoặc `Class.method` và dòng liên quan ngay cạnh công thức, nhánh hoặc phép gán. Ưu tiên link đến code khi có thể; không bịa path, symbol hoặc số dòng.
- **Nêu ranh giới truy vết:** nói rõ module nào được xem là nguồn ngoài và dừng ở đó. Phân biệt giá trị đã xác minh với giả định hoặc nơi chưa truy được.
- **Giữ cây dễ đọc:** dùng code block `text` và indentation ổn định. Chỉ thêm đoạn giải thích ngoài cây cho quy ước, kết luận hoặc lưu ý không thể hiện gọn trong cây. Khi cây quá lớn, chia theo output hoặc nhánh độc lập, không cắt mất nguồn và điều kiện.

### Mẫu mong muốn

Ví dụ rút gọn về nguồn của giá vé trên UI (chỉ minh họa cách trình bày):

```text
ticketFare_UI
  → line[i].ticketFare_UI
      (item thường: i = 0; interline: i = 0 chiều đi, i = 1 chiều về)

      → corgi.line[i].publishedFare
          when isPackageRate && !isEnableAOInPackageRate

          corgi.line[i].publishedFare
            → searchAir.line[i].publishedFare
                (corgi chỉ đọc; AirSearchResponse.scala:687)

                searchAir.line[i].publishedFare
                  → searchAir.pexFareList[ptc].fareForOnePerson
                      when goods.getPackageRate() == FLG_ON
                      (AirWebServiceUtil.getPublishedFare)
                  → không có field
                      otherwise

      → corgi.line[i].ticketFare + cashBack
          otherwise

          corgi.line[i].ticketFare
            → searchAir.line[i].ticketTax
                (corgi chỉ đọc; AirSearchResponse.scala:688)

                searchAir.line[i].ticketTax
                  → gw.fareForOnePerson + searchAir.markup.amount
                      when GALI
                  → Σ(flight.getAdultFare()) + searchAir.markup.amount
                      when LCC

          cashBack
            → -corgi.line[i].markedUpInformation.amount
                when isPex && có markedUpInformation
            → 0
                otherwise
```

Mẫu chỉ thể hiện cách tổ chức thông tin. Khi phân tích thực tế, phải bổ sung đầy đủ điều kiện, phép tính, nguồn của các giá trị trung gian và vị trí code đã xác minh. Dừng ở ranh giới mà người dùng yêu cầu; không mặc định truy sâu vào hệ thống bên ngoài.

### Khi câu hỏi là bug hoặc thay đổi code

Giữ cây nguồn gốc hoặc sơ đồ tương ứng làm trọng tâm nếu nó giúp kiểm chứng. Bổ sung ngắn gọn: điểm sửa trong flow; behavior trước/sau; output và side effect; test hoặc command kiểm chứng. Khi vấn đề phụ thuộc thứ tự gọi, dùng sequence/flowchart theo quy tắc "Chọn hình thức giải thích" thay vì ép mọi vấn đề vào cây giá trị.

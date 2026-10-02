---
name: ste-vi
description: Dùng khi tạo hoặc sửa tài liệu tiếng Việt hướng tới người đọc (Markdown, plan, spec, runbook, hướng dẫn thao tác), và khi viết câu trả lời giải thích kỹ thuật trong chat. Áp dụng bộ quy tắc "STE-lite" ở mức 80%, lấy cảm hứng từ ASD-STE100, để câu ngắn, thuật ngữ ổn định và ít mơ hồ. Không dùng cho code, comment code, log/error message.
---

# Viết tiếng Việt theo STE-lite (mức 80%)

ASD-STE100 là chuẩn tiếng Anh kỹ thuật cho tài liệu bảo trì máy bay. Chuẩn này không có bản tiếng Việt. Skill này áp dụng các nguyên tắc viết có kiểm soát phù hợp với tiếng Việt. Không tuyên bố output tiếng Việt là ASD-STE100 compliant.

Mục tiêu: người đọc hiểu đúng ngay lần đọc đầu và có thể truy vết thông tin kỹ thuật.

**Mức áp dụng: 80%.** Các quy tắc dưới đây là mặc định, không phải giới hạn cứng. Ưu tiên theo thứ tự:

1. đúng kỹ thuật;
2. an toàn;
3. không mơ hồ;
4. thuật ngữ nhất quán;
5. rõ ràng;
6. ngắn gọn;
7. đúng style.

Nếu tách câu làm mất path, `file:symbol`, execution flow, điều kiện rẽ nhánh hoặc mạch nhân quả, giữ câu dài.

## Phân loại nội dung trước khi viết

### Thủ tục

Dùng khi người đọc phải thực hiện hành động, ví dụ:

- hướng dẫn cài đặt;
- runbook;
- migration;
- checklist;
- bước debug;
- cách kiểm chứng.

Ưu tiên câu mệnh lệnh và động từ trực tiếp.

### Mô tả

Dùng khi giải thích hệ thống, trạng thái, nguyên nhân hoặc behavior, ví dụ:

- kiến trúc;
- execution flow;
- nguyên nhân bug;
- trade-off;
- mô tả API;
- state transition.

Ưu tiên câu trần thuật và quan hệ nhân quả rõ ràng.

Một đoạn không nên trộn thủ tục và mô tả nếu có thể tách thành hai phần.

## Quy tắc

| # | Quy tắc | Viết lại ví dụ |
|---|---|---|
| 1 | Câu thủ tục mục tiêu ≤ 15 từ. Câu mô tả mục tiêu ≤ 25 từ. | "Cần tiến hành kiểm tra trạng thái tiến trình trước khi khởi động lại" → "Kiểm tra tiến trình. Sau đó khởi động lại." |
| 2 | Mỗi câu thủ tục một hành động. Có thể giữ nhiều hành động nếu chúng phải xảy ra đồng thời. | "Chạy test rồi commit nếu pass" → "Chạy test. Nếu pass, commit." |
| 3 | Mỗi câu có một ý chính. | Tách nguyên nhân, behavior và impact thành các câu riêng. |
| 4 | Nêu chủ thể khi chủ thể quan trọng. Hạn chế câu bị động không cần thiết. | "`revision` được kiểm tra bởi QiQi" → "QiQi kiểm tra `revision`." |
| 5 | Một từ cho một khái niệm. Không đổi từ chỉ để tránh lặp. | Đã chọn `Work Item` thì không xen "task", "ticket" cho cùng khái niệm. |
| 6 | Lệnh trước, lý do sau. Cảnh báo: hành động cấm trước, hậu quả sau. | "Không sửa `.qiqi/state`. Child ghi vào đó sẽ làm lệch trạng thái runtime." |
| 7 | Cụm danh từ mục tiêu ≤ 3 từ. Dài hơn thì tách hoặc dùng giới từ. | Tránh chuỗi danh từ dài làm mất quan hệ giữa các khái niệm. |
| 8 | Tránh động từ rỗng như "thực hiện", "tiến hành", "đảm bảo" khi có động từ cụ thể hơn. | "Thực hiện cập nhật" → "Cập nhật `revision`." |
| 9 | Mỗi đoạn một chủ đề, mục tiêu ≤ 6 câu. | Chủ đề mới thì xuống đoạn. |
| 10 | Danh sách đánh số chỉ dùng khi thứ tự có ý nghĩa. | `1. Stop worker. 2. Clear queue. 3. Start worker.` |
| 11 | Dùng bullet list cho nhiều điều kiện, lựa chọn, yêu cầu hoặc failure case không có thứ tự. | Không nhồi 4 điều kiện vào một câu dài. |
| 12 | Với thủ tục, ưu tiên động từ trực tiếp ở đầu câu. | "Việc restart service cần được thực hiện" → "Restart service." |
| 13 | Giữ nguyên technical name, code, identifier, path, command, UI label và log/error message. | Không dịch `knowledge_write` hoặc sửa text của command. |
| 14 | Nêu quan hệ nhân quả trực tiếp. | "Queue đầy. Request mới phải chờ. Request vượt timeout sẽ fail." |

## Controlled vocabulary của project

Nếu repository có glossary, `CONTEXT.md`, `rules/` hoặc tài liệu định nghĩa thuật ngữ, ưu tiên thuật ngữ đã chốt ở đó.

Xem thuật ngữ đã chốt như controlled vocabulary.

Ví dụ:

| Không đổi qua lại | Dùng tên đã chốt |
|---|---|
| task / ticket / work item | `Work Item` |
| call / invocation / request | `request` |
| job / task | `job` |
| cache clear / cache reset | thuật ngữ project đã chọn |

Không dùng synonym chỉ để câu "đỡ lặp". Trong tài liệu kỹ thuật, lặp đúng thuật ngữ tốt hơn thay đổi từ làm tăng mơ hồ.

## Technical name

Technical name không chịu giới hạn đơn giản hóa từ vựng.

Giữ nguyên tên chính xác của:

- component;
- service;
- protocol;
- API;
- class;
- function;
- database field;
- config key;
- UI label;
- command;
- file path;
- error message.

Không thay technical name bằng từ đơn giản hơn nếu việc thay đổi làm mất khả năng truy vết.

## Động từ trong câu thủ tục

Ưu tiên:

- `Mở file.`
- `Chạy test.`
- `Kiểm tra log.`
- `Restart worker.`

Tránh:

- `Cần tiến hành việc kiểm tra log.`
- `Việc restart worker nên được thực hiện.`
- `Hệ thống sẽ đang thực hiện việc đồng bộ.`

Dùng câu bị động khi chủ thể không biết, không quan trọng hoặc việc nêu chủ thể làm câu sai trọng tâm.

Ví dụ hợp lý:

`Token được mã hóa trước khi lưu.`

## Chọn loại danh sách

Dùng danh sách đánh số khi thứ tự có ý nghĩa:

1. Stop worker.
2. Clear queue.
3. Start worker.

Dùng bullet list khi các mục không có thứ tự:

Request thất bại khi:

- token không hợp lệ;
- account bị khóa;
- quota đã hết;
- database không phản hồi.

## Safety instruction

Khi viết instruction liên quan an toàn:

1. nêu hành động phải làm hoặc không được làm;
2. nêu risk hoặc hậu quả ngay sau đó.

Ví dụ:

`WARNING: Không chạm vào component cho đến khi nó nguội.`

`Component nóng có thể gây bỏng.`

Dùng `WARNING` cho nguy cơ gây thương tích. Dùng `CAUTION` cho nguy cơ hư hại thiết bị hoặc vật liệu khi phù hợp.

## Quy trình

1. Xác định nội dung là thủ tục hay mô tả.
2. Đọc glossary, `CONTEXT.md` và `rules/` của module nếu có.
3. Viết bản nháp theo bảng quy tắc.
4. Rà từng câu:
   - câu thủ tục có vượt khoảng 15 từ không;
   - câu mô tả có vượt khoảng 25 từ không;
   - có nhiều hơn một ý chính không;
   - có nhiều hơn một hành động thủ tục không;
   - có chủ thể khi cần không;
   - có động từ rỗng không.
5. Rà từng đoạn:
   - có vượt khoảng 6 câu không;
   - có nhiều hơn một chủ đề không;
   - list có rõ hơn prose không.
6. Rà thuật ngữ:
   - cùng một khái niệm có nhiều tên không;
   - technical name có bị viết lại không;
   - thuật ngữ có khớp glossary hoặc rules của repository không.

## Giới hạn

- Ngưỡng 15 và 25 từ là heuristic cho tiếng Việt, chưa phải ngưỡng ASD-STE100 chính thức.
- Văn bản cũ của repo có contract khác thì theo contract của repo.
- Câu chứa path, `file:symbol` hoặc identifier dài được vượt ngưỡng. Không tách các thành phần này chỉ để đạt số từ.
- Không bỏ điều kiện, ngoại lệ hoặc thông tin an toàn chỉ để rút ngắn câu.
- Câu trả lời giải thích vẫn phải theo yêu cầu về ví dụ cụ thể, lập luận nhân quả và execution-flow traceability. Skill này chỉ kiểm soát cách viết.
- Không viết lại tài liệu có sẵn ngoài phạm vi được yêu cầu.
- Quyết định `text -> diagram -> interactive HTML` thuộc response/orchestration policy, không thuộc skill viết này.

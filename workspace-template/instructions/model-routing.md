# Model Routing cho QiQi

Tệp này ghi model Codex đã được xác nhận để QiQi truyền vào MCP tool
`delegate_repo_task` khi cần override model mặc định.

Không suy đoán model từ trí nhớ. Chỉ giữ model thực sự khả dụng trong môi trường
hiện tại.

## Profiles

Trong setup, thay placeholder bằng dữ liệu đã xác nhận. Xóa profile không dùng.

| Profile | Model ID | Reasoning effort | Dùng khi | Evidence khả dụng |
|---|---|---|---|---|
| `fast` | `{{FAST_MODEL_ID}}` | `{{FAST_EFFORT}}` | Task cơ học, phạm vi nhỏ, yêu cầu rõ, verification trực tiếp. | `{{FAST_EVIDENCE}}` |
| `balanced` | `{{BALANCED_MODEL_ID}}` | `{{BALANCED_EFFORT}}` | Implementation thông thường, bug vừa phải, test hoặc tài liệu kỹ thuật. | `{{BALANCED_EVIDENCE}}` |
| `deep` | `{{DEEP_MODEL_ID}}` | `{{DEEP_EFFORT}}` | Kiến trúc, migration, contract phức tạp hoặc bug khó. | `{{DEEP_EVIDENCE}}` |
| `verifier` | `{{VERIFIER_MODEL_ID}}` | `{{VERIFIER_EFFORT}}` | Review độc lập, đối chiếu spec, rủi ro và chất lượng evidence. | `{{VERIFIER_EVIDENCE}}` |

`Reasoning effort` chỉ dùng một trong: `low`, `medium`, `high`, `xhigh` và phải
được model hiện tại hỗ trợ.

## Quy tắc Chọn

1. Xác định loại task và mức rủi ro.
2. Chọn profile thấp nhất vẫn đủ tin cậy.
3. Truyền `Model ID` vào argument `model` của `delegate_repo_task`.
4. Truyền `Reasoning effort` vào argument `reasoning_effort`.
5. Không truyền native CLI arguments, sandbox option, session ID hoặc concurrency
   setting qua QiQi; MCP server sở hữu execution mechanics.
6. Chỉ chuyển sang profile mạnh hơn khi có evidence model trước bỏ sót constraint,
   lặp lỗi suy luận hoặc không xử lý được độ phức tạp của task.

Không đổi model vì thiếu dependency, quyền truy cập, environment failure hoặc
product requirement chưa rõ.

## Default

Nếu QiQi không cần override model, có thể bỏ `model` và `reasoning_effort` khi
gọi tool để child Codex dùng default đã cấu hình trong môi trường.

Model routing không chứa session lifecycle, resume arguments hoặc concurrency.
Policy hiện tại luôn có một active `delegate_repo_task` tại một thời điểm.

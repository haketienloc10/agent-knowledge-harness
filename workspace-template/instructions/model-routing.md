# Model Routing cho QiQi

Tệp này là registry vận hành cho agent kind và model mà QiQi có thể dùng khi
khởi động coding agent trong repository con.

Không dùng trí nhớ từ phiên trước để suy đoán model đang khả dụng. Model picker,
provider config và CLI đang cài trên máy là nguồn sự thật.

## Nguyên tắc Cập nhật

- Ghi đúng agent kind Herdr hỗ trợ và đúng model ID cần truyền cho agent.
- Ghi native arguments hoàn chỉnh đặt sau `--` của `herdr agent start`, gồm model
  và chế độ permission phù hợp.
- Ghi native resume arguments chính xác cho agent kind đó. Nếu không hỗ trợ
  resume, ghi `Not supported — <lý do>` thay vì đoán cú pháp.
- Chỉ ghi model đã xác nhận có thể khởi động trong môi trường hiện tại.
- Ghi evidence availability: model picker, provider config hoặc lần start thành
  công.
- Mô tả điểm mạnh và điểm yếu bằng task thực tế đã quan sát.
- Xóa hàng không dùng thay vì giữ placeholder hoặc model đã mất quyền truy cập.
- Cập nhật khi provider, quota, model catalog hoặc concurrency thay đổi.

## Inventory Model Đang Khả dụng

Trong setup, thay toàn bộ placeholder bằng dữ liệu thực tế. Có thể thêm hoặc xóa
hàng để khớp đúng inventory.

| Agent kind | Model ID chính xác | Native arguments | Native resume arguments | Evidence khả dụng | Điểm mạnh | Điểm yếu | Nên dùng cho | Không nên dùng cho | Reasoning effort | Giới hạn song song |
|---|---|---|---|---|---|---|---|---|---|---|
| `{{AGENT_1_KIND}}` | `{{MODEL_1_ID}}` | `{{AGENT_1_ARGUMENTS}}` | `{{AGENT_1_RESUME_ARGUMENTS}}` | `{{MODEL_1_EVIDENCE}}` | `{{MODEL_1_STRENGTHS}}` | `{{MODEL_1_WEAKNESSES}}` | `{{MODEL_1_USE_CASES}}` | `{{MODEL_1_AVOID}}` | `{{MODEL_1_EFFORT}}` | `{{MODEL_1_CONCURRENCY}}` |
| `{{AGENT_2_KIND}}` | `{{MODEL_2_ID}}` | `{{AGENT_2_ARGUMENTS}}` | `{{AGENT_2_RESUME_ARGUMENTS}}` | `{{MODEL_2_EVIDENCE}}` | `{{MODEL_2_STRENGTHS}}` | `{{MODEL_2_WEAKNESSES}}` | `{{MODEL_2_USE_CASES}}` | `{{MODEL_2_AVOID}}` | `{{MODEL_2_EFFORT}}` | `{{MODEL_2_CONCURRENCY}}` |
| `{{AGENT_3_KIND}}` | `{{MODEL_3_ID}}` | `{{AGENT_3_ARGUMENTS}}` | `{{AGENT_3_RESUME_ARGUMENTS}}` | `{{MODEL_3_EVIDENCE}}` | `{{MODEL_3_STRENGTHS}}` | `{{MODEL_3_WEAKNESSES}}` | `{{MODEL_3_USE_CASES}}` | `{{MODEL_3_AVOID}}` | `{{MODEL_3_EFFORT}}` | `{{MODEL_3_CONCURRENCY}}` |

`Giới hạn song song` là **capability metadata của model/provider**, không phải
quyền cho QiQi chạy nhiều delegated turn cùng lúc. `AGENTS.md` hiện quy định một
phiên QiQi chỉ có một active delegated turn tại một thời điểm.

## Profile Định tuyến

Một model có thể phục vụ nhiều profile.

| Profile | Agent kind | Model ID | Dùng khi | Chuyển profile khi |
|---|---|---|---|---|
| `fast` | `{{FAST_AGENT_KIND}}` | `{{FAST_MODEL_ID}}` | Task cơ học, phạm vi nhỏ, yêu cầu rõ, ít file và verification trực tiếp. | Scope mở rộng, cần suy luận liên module hoặc model lặp lại lỗi suy luận. |
| `balanced` | `{{BALANCED_AGENT_KIND}}` | `{{BALANCED_MODEL_ID}}` | Implementation thông thường trong một repo, điều tra bug vừa phải, viết test và tài liệu kỹ thuật. | Có breaking contract, migration, kiến trúc phức tạp hoặc nhiều lần verification fail. |
| `deep` | `{{DEEP_AGENT_KIND}}` | `{{DEEP_MODEL_ID}}` | Phân tích kiến trúc, cross-repo contract, migration, bug khó tái hiện hoặc nhiều trade-off. | Không tự hạ profile trong cùng task nếu chưa có evidence task đã trở nên cơ học. |
| `verifier` | `{{VERIFIER_AGENT_KIND}}` | `{{VERIFIER_MODEL_ID}}` | Review độc lập, đối chiếu spec, rủi ro và chất lượng evidence. | Không dùng cùng context triển khai nếu mục tiêu là đánh giá độc lập. |

## Quy tắc Chọn Model

1. Xác định loại công việc: điều tra, implementation, migration, cross-repository
   contract, verification hoặc tác vụ cơ học.
2. Xác định rủi ro: phạm vi file, breaking change, dữ liệu, bảo mật, rollback và
   dependency bên ngoài.
3. Chọn profile thấp nhất vẫn đủ tin cậy.
4. Lấy agent kind, model ID và native arguments chính xác từ inventory.
5. Khi resume, lấy native resume arguments từ đúng hàng inventory và kết hợp với
   session ID đã lưu; không suy ra từ native arguments khởi động mới.
6. Đọc concurrency/capacity chỉ như metadata môi trường; không dùng nó để bypass
   lifecycle serialization trong `AGENTS.md`.
7. Ghi lựa chọn trong task context khi nó ảnh hưởng chi phí, độ trễ hoặc chất
   lượng.

## Quy tắc Chuyển Model

Chỉ chuyển sang model mạnh hơn khi có evidence về giới hạn năng lực, ví dụ:

- bỏ sót constraint đã có trong prompt hoặc artifact;
- không giữ được quan hệ giữa nhiều repository;
- lặp lại cùng một lỗi suy luận sau feedback rõ;
- không tạo được kế hoạch rollback hoặc migration nhất quán;
- review độc lập phát hiện lỗi hệ thống qua nhiều vòng.

Không chuyển model chỉ vì thiếu dependency, quyền truy cập, command môi trường
fail, repository thiếu tài liệu, yêu cầu chưa rõ hoặc test baseline đang đỏ.

## Concurrency Metadata

- Ghi giới hạn model/provider để phục vụ capacity planning và thay đổi policy
  trong tương lai.
- Metadata này không cho phép QiQi tạo active turn thứ hai.
- Policy thực thi hiện tại luôn theo `AGENTS.md`: turn mới chỉ bắt đầu sau khi turn
  hiện tại terminally complete và đã reconcile.

## Output QiQi Cần Ghi nhận

Khi tạo phiên, QiQi cần biết repository, task, profile, agent kind, model ID,
native arguments, reasoning effort, dependency và lý do lựa chọn nếu không dùng
profile mặc định.

Khi đóng một phiên có thể cần tiếp tục, QiQi phải lưu native session ID. Khi
resume, QiQi phải dùng native resume arguments từ inventory cùng session ID đó.

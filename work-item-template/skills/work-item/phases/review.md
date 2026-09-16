# Review / acceptance gate

Mandatory trước khi tracked Work Item được mark done hoặc treated ready for final reporting.

Implementation tồn tại, child nói "done", hoặc tests pass riêng lẻ không establish Work Item completion.

## Core rule

Tách ba khái niệm:

- **implemented** — code/config/data change tồn tại;
- **verified** — relevant evidence demonstrate actual behavior;
- **accepted** — current acceptance criteria satisfied hoặc explicit authorized deviation được accept.

Không collapse chúng thành một status.

## Assessment

### Acceptance assessment

Với mỗi material current acceptance criterion:

- criterion;
- actual evidence;
- assessment: `satisfied | not-satisfied | unresolved`;
- next action nếu not satisfied/unresolved.

Không mark satisfied dựa chỉ trên implementation intent hoặc agent assertion.

### Deviations

Behavior khác current requirement/plan và classify:

- implementation defect cần fix;
- verified equivalent outcome;
- material product/contract deviation cần user acceptance.

### Missing evidence

Verification chưa thực sự chạy. Không fabricate test, deployment, branch, commit hoặc environment evidence.

### Blocking questions

Chỉ question có answer thay completion/acceptance. Dùng `none` nếu không có.

### Gate

- `ready` — mọi material acceptance criteria satisfied/accepted bằng actual evidence và không còn blocking question.
- `needs_user_clarification` — completion phụ thuộc explicit user acceptance của material deviation hoặc unresolved product/domain expectation.
- `needs_discovery` — cần thêm verification/remediation/objective evidence và agent có thể tiếp tục không cần user decision.
- `blocked` — required verification/evidence không obtain được vì external dependency/environment unavailable.

Với `needs_discovery`, state exact next agent action: verify, reproduce, fix, gather evidence hoặc re-investigate.

## Requirement drift

Review theo **current Work Item revision**, không theo obsolete delegated revision/original wording.

- changed requirement → quay intake reconciliation;
- factual contradiction → quay investigation;
- implementation gap → quay implementation/verification.

## Reporting boundary

`ready` cho phép proceed tới required final reporting/completion assessment; không authorize fabricate report field không supported bởi stored current state/evidence.

## Persistence

QiQi reconcile current acceptance evidence/gaps vào `review.md` và `WORK_ITEM.md`. Không tạo review-session/history files; giữ chỉ material evidence và unresolved completion state.

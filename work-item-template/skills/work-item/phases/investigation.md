# Investigation gate

Conditional. Dùng khi intake đã đủ rõ nhưng investigation target/boundary chưa rõ. Nếu target, ownership và required evidence đã obvious từ Work Item + repo context thì bỏ qua clarification ceremony và điều tra trực tiếp.

Gate này scope investigation; không thay `investigation.md` và không thay actual investigation.

## Core rule

Prefer **discovery over user questioning** cho factual uncertainty.

Không hỏi user repo/module/class nào owns behavior khi `repos.yaml`, source, tests, docs, runtime config hoặc existing evidence có thể establish.

Chỉ hỏi user khi investigation đã expose genuine product/domain ambiguity: nhiều behavior đều technically plausible và authoritative repo/docs không xác định intended semantics.

## Clarification targets

Resolve/classify:

- symptom / behavior cần trace;
- authoritative source of truth;
- repository/module/service ownership;
- investigation boundary;
- evidence cần để phân biệt competing explanations;
- cross-repo dependency materially đổi scope;
- intake assumptions cần factual validation.

## Assessment

### Known
Minimum relevant facts đã established.

### Unknowns to discover
Factual/technical unknowns agent có thể tự investigate.

### Proposed investigation target
Best first boundary/entry point và vì sao informative.

### Discovery path
Bounded sequence, ví dụ:

1. trace relevant entry point;
2. identify authoritative ownership/data flow;
3. verify observed behavior against tests/config/docs;
4. stop + reconcile scope nếu ownership cross material new boundary.

Không expand thành full implementation plan.

### User decision needed
Chỉ unresolved product/domain choice không thể establish bằng authoritative evidence. Dùng `none` nếu không có.

### Gate

- `ready` — investigation target/boundary đủ rõ để proceed hoặc conclusion đủ cho planning.
- `needs_user_clarification` — evidence expose material product/domain ambiguity cần user intent.
- `needs_discovery` — cần thêm factual/repository/evidence work và agent tự làm được.
- `blocked` — required source/system/dependency inaccessible, ngăn meaningful investigation.

## Boundary changes

Khi discovery ra repo/module khác:

- không coi new boundary là requirement change tự động;
- update investigation scope nếu cần để trả lời requirement hiện tại;
- chỉ quay intake nếu discovery thực sự đổi product scope, acceptance hoặc user-visible behavior.

## Persistence

QiQi merge/rewrite material scope/findings/questions vào `investigation.md` và `WORK_ITEM.md` như living current state. Không tạo clarification file, chronological note hay execution diary. Preserve evidence/provenance chỉ khi còn cần support current finding hoặc future acceptance assessment.

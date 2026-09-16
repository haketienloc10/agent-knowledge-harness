# Planning gate

Conditional. Dùng sau investigation khi implementation không nên bắt đầu cho tới khi current approach/material decisions explicit. Skip khi approach straightforward, reversible, consistent với architecture/convention và evidence đã đủ.

## Core rule

**Agent-owned technical choices should stay agent-owned.**

Agent tự chọn + justify normal implementation detail khi evidence đủ và choice reversible hoặc governed bởi existing repository conventions.

Chỉ hỏi user khi decision đổi product behavior, public/external contract, data semantics, compatibility expectation, operational risk, irreversible migration/destructive action hoặc material trade-off không derive được từ current requirements.

Không hỏi user chọn giữa implementation styles chỉ vì có nhiều cách kỹ thuật.

## Assessment

### Proposed solution
Current approach ở mức đủ để execution coherent; tránh line-by-line coding plan.

### Why this approach
Tie approach vào verified findings, current requirements và repo/system constraints.

### Affected boundaries
Material repos/modules/APIs/schemas/jobs/operational surfaces cần touch hoặc preserve.

### Alternatives
Giữ alternative chỉ khi rejection rationale còn material để tránh lặp bad direction hoặc giải thích meaningful trade-off. Bỏ routine alternatives.

### Verification strategy
Cách demonstrate acceptance, gồm compatibility/regression checks khi material.

### Risks
Chỉ material risks + mitigation/verification.

### User decision needed
Dùng `none` trừ khi còn material product/contract/irreversible trade-off.

### Gate

- `ready` — approach, boundaries, material risks và verification đủ cho implementation.
- `needs_user_clarification` — material trade-off/product/contract decision cần user intent.
- `needs_discovery` — cần thêm technical/evidence work trước khi chọn responsible approach và agent tự làm được.
- `blocked` — planning không thể proceed vì required dependency/decision/source unavailable.

## Change control

Nếu planning reveal current requirement/acceptance phải đổi, quay intake gate thay vì silently rewrite product intent.

Nếu chỉ reveal factual gap, quay investigation/discovery mà không hỏi user.

## Persistence

QiQi reconcile material current approach/decision/risk/verification vào `30_plan.md`, `00_WORK_ITEM.md` Decisions/Next Actions và existing living state. Không tạo plan-history, decision-session hoặc clarification files.

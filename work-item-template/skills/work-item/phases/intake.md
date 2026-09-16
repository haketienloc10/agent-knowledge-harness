# Intake gate

Mandatory cho Work Item mới và material requirement change. Mục tiêu là establish effective requirement đủ rõ để investigation tiếp tục mà không đoán product intent; không điều tra code ở gate này.

## Core rule

**Clarify meaning, not mechanics.**

Ask user chỉ cho intent, product/domain semantics, acceptance, scope, constraints, irreversible choice hoặc decision không thể establish authoritatively bằng docs/repository/reference discovery.

Không hỏi user chọn repository/module/class/implementation pattern/test command khi agent có thể tự discover.

## Classify uncertainty

1. **Requirement unknown** — chỉ user/product owner quyết định được → hỏi user.
2. **Domain/terminology unknown** — nêu current interpretation + source; nếu authoritative material có thể resolve thì discovery trước khi hỏi.
3. **Implementation unknown** — không hỏi user; handoff sang investigation.
4. **Safe reversible assumption** — nói rõ assumption và tiếp tục nếu sai có thể detect/reverse rẻ.

Không silently biến unknown product requirement thành implementation assumption.

## Assessment

Khi material, trình bày ngắn:

### Understanding
- agent hiểu mục tiêu gì;
- expected outcome / externally visible behavior.

### Known scope
- in scope;
- out of scope chỉ khi tránh likely misunderstanding;
- material constraints.

### Terms / concepts
Với term quan trọng nhưng ambiguous: term, current interpretation, evidence/source, còn cần clarification hay không. Không tạo glossary cho ordinary terms đã rõ.

### Material ambiguities
Chỉ những ambiguity có thể đổi requirement, acceptance, scope hoặc externally visible behavior.

### Proposed acceptance
Acceptance criteria đủ concrete để về sau biết task done hay chưa; không invent product expectation.

### Discovery handoff
Factual/module/repository questions investigation có thể tự trả lời mà không cần user.

### Gate
Return đúng một state:

- `ready` — requirement meaning, material scope và acceptance đủ rõ; remaining unknowns là implementation/discovery facts.
- `needs_user_clarification` — material intent/product/domain decision cần user.
- `needs_discovery` — authoritative factual/domain lookup nên chạy trước khi finalizing requirement, chưa cần user decision.
- `blocked` — required external dependency/source unavailable làm progress impossible.

## Ready criteria

`ready` yêu cầu objective hiểu được, material scope đủ bounded, acceptance đủ concrete, không còn ambiguity có thể materially đổi product intent, và remaining technical/module unknowns có thể giao investigation.

Biết exact repository/module **không phải** điều kiện intake readiness.

## Persistence

Gate không được tạo orphan directory. Với Work Item mới, resolve/validate candidate path trước nhưng chỉ tạo dossier khi đồng thời materialize revision-1 `00_WORK_ITEM.md`.

QiQi MUST persist current semantic state trước khi pause/return từ intake:

- `ready` → `status: active`, `phase: intake`, effective requirement/acceptance hiện tại;
- `needs_discovery` → `status: active`, `phase: intake`, factual unknowns + exact next discovery action;
- `needs_user_clarification` → `status: waiting`, `phase: intake`, current understanding + material open question(s);
- `blocked` → `status: blocked`, `phase: intake`, blocker + điều kiện unblock.

Với existing Work Item/material change, reconcile cùng mapping vào current canonical state và tăng revision khi completion-relevant state đổi material.

QiQi reconcile chỉ material current truth vào `00_WORK_ITEM.md` và khi hữu ích `10_intake.md`. Không persist question/answer chronology, transcript, discarded wording hoặc routine reasoning.

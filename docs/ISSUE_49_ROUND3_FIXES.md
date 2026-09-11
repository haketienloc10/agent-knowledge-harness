# Issue #49 — Round 3 low-risk fixes

Tài liệu này ghi lại hai thay đổi low-risk đầu tiên được chọn từ rollout corpus của issue #49. Scope cố ý không bao gồm tối ưu `instructions/model-routing.md`; routing-policy hydration sẽ được đo A/B riêng sau khi hai thay đổi này ổn định.

## 1. Incremental Work Item mutation: omission khác explicit null

Runtime incremental mutation đã có semantic contract:

```text
field omitted  -> không thay đổi field đó
field = null   -> invalid; caller phải omit field
```

Trước thay đổi này, một số declared mutation fields dùng annotation nullable để biểu diễn giá trị mặc định khi field bị omit. Pydantic JSON Schema vì vậy quảng bá `null` là input hợp lệ dù runtime validator reject explicit `null`. Rollout thực tế đã tạo một parent retry chỉ để bỏ `answer: null` khỏi `question_upsert`.

Contract sau thay đổi:

- declared incremental mutation field vẫn optional/omittable;
- generated schema không quảng bá `null` là giá trị hợp lệ cho field đó;
- runtime vẫn reject explicit `null` để giữ semantics hiện tại;
- current-state merge-patch semantics không đổi: nơi nào `null` có nghĩa xóa/reset theo contract vẫn giữ nullable.

Regression coverage phải kiểm tra cả generated schema và runtime validation, không chỉ một phía.

## 2. Dynamic tool-schema discovery phải exact và bounded

Khi exact tool name đã biết từ public boundary/policy, QiQi không cần enumerate toàn bộ namespace/family để lấy lại schema. Broad discovery như:

```text
ALL_TOOLS.filter(...includes("knowledge_"))
ALL_TOOLS.filter(...includes("work_item_"))
```

có thể append schema của nhiều sibling tools vào parent context. Context đó tiếp tục được xử lý ở các inference sau dù current action chỉ cần một tool.

Policy sau thay đổi:

```text
exact tool known
-> load/call exact tool schema

exact tool unknown
-> narrow discovery
-> stop khi candidate cần thiết đã resolve
```

Không thay đổi Work Item, Shared Knowledge hoặc delegation semantics; đây chỉ là giới hạn discovery surface.

## Verification target

PR cho hai fix này phải chứng minh:

1. declared incremental mutation fields omittable nhưng không nullable trong generated schema;
2. explicit-null runtime validation vẫn giữ nguyên;
3. workspace policy khóa exact/bounded tool discovery và cấm family-wide dump cho known tool;
4. existing Work Item/QiQi Delegate contract tests vẫn pass;
5. không thay đổi `instructions/model-routing.md` trong PR này.

Sau khi merge và có rollout tương đương, issue #49 mới chuyển sang experiment riêng cho extra parent boundary của JIT route-policy hydration.

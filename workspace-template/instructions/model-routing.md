# Route Selection Policy cho QiQi

Tệp này chỉ giúp QiQi **chọn exact `route`** để truyền vào
`delegate_repo_task`. Nó không mô tả cách MCP chạy agent.

`instructions/agent-routing.yaml` là machine source of truth duy nhất cho route
đang tồn tại và cho executable, adapter, model, START/RESUME argv cùng native CLI
flags của từng route.

Không copy model ID, permission mode, effort hay CLI flags vào file này. Khi
runtime configuration thay đổi, chỉ registry machine-readable phải đổi.

## Activation

File này **không phải mandatory startup material**.

Always-on invariant nằm ở `AGENTS.md`:

```text
Default delegation route được resolve just-in-time từ machine-local setup;
fallback = claude-balanced khi local config không tồn tại.
```

Turn không delegate **không đọc** file này hoặc `.qiqi/config.local.json` chỉ để hoàn thành startup.

Khi một turn thực sự cần delegation, QiQi **đọc file này ngay trước route decision** rồi:

1. nếu `.qiqi/config.local.json` tồn tại, đọc file đó và yêu cầu:
   - `version == 1`;
   - `execution_agents` là non-empty list chỉ gồm `claude`/`codex`;
   - `default_route` tồn tại trong `agent-routing.yaml` và route đó thuộc một agent đã enable;
2. chỉ xét route thuộc `execution_agents` đã enable;
3. nếu local config không tồn tại, coi cả route registry là available và dùng `claude-balanced` làm fallback;
4. user/project explicit route vẫn phải tồn tại trong registry **và** thuộc enabled execution agents khi local config có mặt.

`.qiqi/config.local.json` là machine-local execution preference/capability selection, không phải product/task truth và không được copy vào Work Item hay TaskPacket.

Mục tiêu của activation rule là tránh fixed context tax cho status-only/answer-only
turn nhưng không đánh đổi route-selection correctness ở các turn thực sự delegate.

## Route hiện có

### `claude-fast`

Dùng cho task nhỏ, cơ học và có phạm vi rõ, khi:

- thay đổi hẹp và ít uncertainty;
- expected outcome cụ thể;
- verification trực tiếp;
- không cần reasoning kiến trúc đáng kể.

### `claude-balanced`

Balanced route cho phần lớn repo-local implementation khi Claude được enable, gồm:

- feature/bugfix thông thường;
- refactor có phạm vi vừa;
- test hoặc docs kỹ thuật gắn với implementation;
- investigation cần reasoning ở mức vừa nhưng chưa phải bài toán kiến trúc sâu.

Khi Claude là enabled default agent và không có lý do rõ cho fast/deep/verifier, dùng `claude-balanced`.

### `claude-deep`

Dùng khi task có uncertainty hoặc reasoning cost cao, ví dụ:

- architecture hoặc design trade-off phức tạp;
- migration có nhiều bước/ràng buộc;
- contract thay đổi có blast radius đáng kể;
- bug khó, nguyên nhân chưa rõ hoặc cần reasoning sâu qua nhiều subsystem.

Không chọn route này chỉ vì task dài; chọn vì độ khó reasoning/risk thực sự cao.

### `claude-verifier`

Dùng cho verification/review độc lập khi mục tiêu chính là đánh giá evidence thay
vì implementation, ví dụ:

- review change quan trọng;
- đối chiếu implementation với spec/contract;
- tìm regression/risk sau một delegation khác;
- xác minh claim trước khi QiQi reconcile cross-repo result.

Independence của route này là rollover signal: khi chọn `claude-verifier` cho
independent verification/review, QiQi **MUST START fresh by default** theo semantic
START/RESUME policy trong `AGENTS.md`. Không reuse implementation native session chỉ
vì verifier dùng cùng underlying native agent family. Chỉ RESUME khi task explicitly
không còn yêu cầu independence và QiQi có affirmative reason cần exact native
continuity.

Nếu verifier phát hiện cần implementation mới, QiQi quyết định delegation tiếp
theo; verifier không mặc nhiên trở thành implementation route.

### `codex-balanced`

Balanced route cho repo-local work khi Codex được enable hoặc được chọn làm machine-local default. Dùng khi:

- `.qiqi/config.local.json.default_route` là `codex-balanced`;
- người dùng hoặc project policy chỉ định Codex;
- task phụ thuộc capability/integration đã được xác minh là phù hợp riêng với Codex.

Không chọn Codex chỉ để retry một environment/runtime failure của route khác.

## Quy tắc chọn route

1. Resolve enabled execution agents/default route theo Activation ở trên.
2. Xác định outcome, scope, risk và uncertainty của repo-local task.
3. Chọn route nhẹ nhất vẫn đủ tin cậy trong tập route đã enable.
4. Nếu không có tín hiệu rõ cho route specialized, dùng exact machine-local `default_route`; nếu local config không tồn tại thì dùng `claude-balanced`.
5. Truyền **exact route name** vào `delegate_repo_task`; không truyền profile name.
6. Không đặt executable, model ID, permission mode, effort, hook config hoặc raw CLI flags vào TaskPacket hay public MCP arguments.
7. Nếu route không tồn tại trong `agent-routing.yaml`, route đó không khả dụng dù được nhắc ở tài liệu hay ví dụ khác.
8. Nếu local config có mặt nhưng route thuộc agent không nằm trong `execution_agents`, route đó không khả dụng.
9. Không đổi route chỉ để né blocker về environment, dependency, permission hoặc product decision; giải quyết blocker thực tế trước.

## Boundary

File này sở hữu duy nhất câu hỏi:

```text
QiQi nên chọn route nào cho task này?
```

Các concern sau **không thuộc route-selection policy** và được mô tả ở artifact
sở hữu tương ứng:

- TaskPacket/prompt semantics → `AGENTS.md` + `identity.md`;
- semantic START/RESUME rollover decision → `AGENTS.md`;
- agent/model/native argv + `{handoff_args}` insertion point → `agent-routing.yaml`;
- Herdr lifecycle, native session identity, Stop-hook capture và SQLite runtime state → MCP;
- dependency/concurrency/delegation waves → `AGENTS.md`;
- setup + multi-phase session rollover smoke → `docs/WORKSPACE_SETUP.md`.

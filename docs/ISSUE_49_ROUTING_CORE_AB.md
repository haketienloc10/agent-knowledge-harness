# Issue #49 — routing-core A/B pilot

## Goal

Test whether ordinary delegation can remove the standalone parent inference caused by just-in-time `instructions/model-routing.md` hydration while preserving route-selection correctness.

This branch is an **experiment harness**, not a production policy change. It intentionally adds no migration and does not modify the checked-in workspace template policy yet.

Baseline remains current `main` behavior:

```text
actual delegation
-> read instructions/model-routing.md
-> parent inference
-> choose route
-> delegate_repo_task
```

Candidate behavior under test:

```text
compact route-selection core already present in AGENTS.md
-> choose route directly
-> delegate_repo_task
```

`instructions/model-routing.md` remains available for extended rationale/edge cases, but is not a ceremonial standalone read on the ordinary delegation path.

## Safety boundary

The candidate core preserves these route semantics:

- `claude-fast`: narrow/mechanical, low uncertainty, direct verification;
- `claude-balanced`: deterministic default for ordinary implementation/refactor/test/docs/investigation;
- `claude-deep`: high uncertainty/reasoning risk, architecture/design trade-offs, constrained migrations or material blast radius;
- `claude-verifier`: independent verification/review and fresh START by default while independence is material;
- `codex-balanced`: explicit user/project request or a specific verified capability reason;
- choose the lightest route still reliable;
- do not switch route merely to bypass environment/dependency/permission blockers;
- exact route must exist in `instructions/agent-routing.yaml`.

TaskPacket, Work Item, Shared Knowledge, START/RESUME runtime identity and exact native result handoff semantics are out of scope and must remain unchanged.

## Reversible transformer

The harness requires Python 3. Use `python3` explicitly; the launcher also detects a legacy Python 2 `python` alias and attempts to re-exec itself with `python3`.

Use the script from this branch against the **real QiQi workspace** used for the rollout:

```bash
python3 scripts/issue49-routing-core-experiment.py \
  --workspace /ABSOLUTE/PATH/TO/QIQI_WORKSPACE \
  --mode check
```

Expected output before the experiment:

```text
baseline
```

Switch to candidate:

```bash
python3 scripts/issue49-routing-core-experiment.py \
  --workspace /ABSOLUTE/PATH/TO/QIQI_WORKSPACE \
  --mode candidate
```

Verify:

```bash
python3 scripts/issue49-routing-core-experiment.py \
  --workspace /ABSOLUTE/PATH/TO/QIQI_WORKSPACE \
  --mode check
```

Expected:

```text
candidate
```

Restore baseline at any time:

```bash
python3 scripts/issue49-routing-core-experiment.py \
  --workspace /ABSOLUTE/PATH/TO/QIQI_WORKSPACE \
  --mode baseline
```

The transformer is fail-closed: it mutates only the exact reviewed baseline/candidate blocks and refuses mixed or unknown policy text. `--dry-run` is available for candidate/baseline mode.

## Pilot protocol: use a two-turn parent session

A fresh one-turn delegation is **not sufficient** to test the primary hypothesis. In the first clean A/B attempt, baseline combined `identity.md`, `repos.yaml`, and `instructions/model-routing.md` into one startup `exec`, so both baseline and candidate had the same parent-inference count. That run measured payload reduction, not removal of a standalone boundary.

The representative condition from the rollout corpus is:

```text
turn 1: startup material already hydrated, no delegation
turn 2: delegation requested
baseline -> standalone model-routing read -> parent inference -> delegate
candidate -> route directly from always-on core -> delegate
```

Therefore every A/B session used for the primary boundary test MUST have two turns.

### Turn 1 — identical warm-up, no delegation

Start a fresh parent QiQi session and send exactly the same warm-up under baseline and candidate:

```text
Đọc các workspace policy/material bắt buộc để xác nhận repository registry và
orchestration context hiện tại. Chỉ chuẩn bị context cho lượt tiếp theo;
không delegate, không sửa file, không đọc instructions/model-routing.md.
Trả lời ngắn rằng context đã sẵn sàng.
```

Expected baseline behavior: hydrate `identity.md` + `repos.yaml`, but do not read `instructions/model-routing.md` because the turn explicitly does not delegate.

Expected candidate behavior: same external action shape. The compact routing core is already in always-on `AGENTS.md`, so this turn also measures the candidate's small fixed always-on tax.

### Turn 2 — balanced delegation

In the **same parent session**, send this exact prompt for both policies:

```text
Trong repository skygserv, thực hiện một lượt investigation read-only trên master
cho segment insurance của MyPage Top C11500.

Truy vết execution flow qua BasketScreenJourneyServiceImpl,
checkInterlineItnAbleApplyInsOrCxlProtect, CSkygateCheck.isInsCheck
và CInsRsvManager.getInsAgtCd.

Xác định lookup lặp, side effect, candidate cache/short-circuit và vị trí
instrumentation phù hợp. Chỉ investigation và báo cáo evidence;
không sửa code hoặc tài liệu.

Hãy delegate repo-local work theo policy hiện tại.
```

Expected route: `claude-balanced`; START fresh (`session_id` omitted).

Collect the whole two-turn parent rollout as one file for baseline and one for candidate.

### Turn 2 — verifier variant

Only after the balanced two-turn pair validates the expected boundary shape, repeat the same two-turn structure with an independent-review prompt. Expected route: `claude-verifier`, fresh START by default.

## Evidence from one-turn balanced v2 pair

The one-turn v2 pair is still useful as a payload/context measurement:

| Metric | Baseline | Candidate | Delta |
| --- | ---: | ---: | ---: |
| Parent inferences | 3 | 3 | 0 |
| Pre-delegation input | 46,293 | 45,510 | -783 (-1.69%) |
| Pre-delegation cached | 27,520 | 27,776 | +256 |
| Pre-delegation uncached | 18,773 | 17,734 | -1,039 (-5.53%) |
| Whole-turn input | 76,038 | 74,184 | -1,854 (-2.44%) |
| Whole-turn cached | 52,352 | 34,176 | -18,176 |
| Whole-turn uncached | 23,686 | 40,008 | +16,322 |
| Selected route | `claude-balanced` | `claude-balanced` | same |
| START/RESUME | START | START | same |
| Startup tool-result size | ~14.7k chars | ~9.7k chars | ~-5.0k chars |
| Child result size | ~12.4k chars | ~11.9k chars | comparable |

Interpretation:

- candidate removed the `model-routing.md` payload from the startup read;
- baseline had no standalone routing boundary in this fresh-session shape because the read was bundled with startup material;
- pre-delegation parent input/uncached input improved modestly under candidate;
- whole-turn cached/uncached totals are not a reliable savings claim in this pair because the final candidate inference had an anomalously low cache hit despite comparable child-result size;
- therefore the primary `-1 parent inference` hypothesis remains **unproven**, not disproven.

## What to collect

For each run, provide only the parent QiQi rollout JSONL. No child rollout is required for issue #49.

Analysis will compare:

- parent inference count per turn and for the whole session;
- cumulative input tokens;
- cached input;
- uncached input;
- output tokens;
- whether a standalone `model-routing.md` read occurred on delegation turn 2;
- selected route;
- START/RESUME mode;
- TaskPacket material equivalence;
- child terminal result shape/wall-time as a confounder check.

Primary hypothesis:

```text
candidate delegation turn after startup context is already hydrated
= same material route decision
+ same correctness invariants
- one standalone routing-hydration parent inference
```

Do not claim exact token savings from the old routing-read inference alone; removing a boundary changes subsequent prompt layout/cache behavior.

## Pilot decision gate

Proceed to a full route matrix only if the two-turn A/B pair shows:

1. turn 1 performs no delegation and baseline does not hydrate `model-routing.md`;
2. same intended route class on turn 2;
3. candidate removes a standalone turn-2 routing read that baseline performs;
4. candidate reduces turn-2 parent inference count and materially reduces cumulative parent input without repeatable abnormal uncached growth;
5. TaskPacket, Work Item, Knowledge, START/RESUME and exact native-result correctness invariants remain unchanged.

If the balanced pair passes, repeat verifier using the same two-turn structure. Only then extend to:

- `claude-fast` A/B x1;
- `claude-balanced` A/B x2 total;
- `claude-deep` A/B x1;
- `claude-verifier` A/B x2 total;
- `codex-balanced` A/B x1;
- no-delegation/status-only A/B x1.

Only after that evidence should the candidate be converted into a permanent policy/checker change with migration coverage.

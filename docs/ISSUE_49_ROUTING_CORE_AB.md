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

## Pilot matrix

Start with four parent rollouts only:

| Run | Policy | Scenario | Expected route |
| --- | --- | --- | --- |
| A1 | baseline | ordinary implementation/bugfix | `claude-balanced` |
| B1 | candidate | materially equivalent ordinary implementation/bugfix | `claude-balanced` |
| A2 | baseline | independent review/verifier | `claude-verifier`, fresh START |
| B2 | candidate | materially equivalent independent review/verifier | `claude-verifier`, fresh START |

Use fresh parent sessions for each run. Keep repository, task semantics, expected outcome and relevant environment as equivalent as practical. Do not intentionally change model/route/session settings between A and B beyond the routing policy state.

## Suggested prompts

Balanced pair:

```text
Trong repo <repo>, thực hiện một bugfix/implementation repo-local có scope rõ,
bao gồm verification phù hợp. Hãy delegate repo-local work theo policy hiện tại.
```

Verifier pair:

```text
Review độc lập change <change> trong repo <repo> so với contract/spec <contract>.
Mục tiêu là đánh giá evidence, regression và risk; không implementation.
Hãy delegate theo policy hiện tại.
```

The concrete task should be real enough to exercise delegation but small enough that child runtime variance does not dominate the parent orchestration comparison.

## What to collect

For each run, provide only the parent QiQi rollout JSONL. No child rollout is required for issue #49.

Analysis will compare:

- parent inference count;
- cumulative input tokens;
- cached input;
- uncached input;
- output tokens;
- whether a standalone `model-routing.md` read occurred;
- selected route;
- START/RESUME mode;
- TaskPacket material equivalence;
- child terminal result shape/wall-time as a confounder check.

Primary hypothesis:

```text
candidate ordinary delegation
= same material route decision
+ same correctness invariants
- one standalone routing-hydration parent inference
```

Do not claim exact token savings from the old routing-read inference alone; removing a boundary changes subsequent prompt layout/cache behavior.

## Pilot decision gate

Proceed to a full route matrix only if both A/B pairs show:

1. same intended route class;
2. verifier still starts fresh;
3. candidate removes the ordinary standalone routing read;
4. candidate reduces parent inference count and materially reduces cumulative parent input without abnormal uncached growth;
5. no TaskPacket/Work Item/Knowledge/runtime correctness invariant changes.

If pilot passes, extend to:

- `claude-fast` A/B x1;
- `claude-balanced` A/B x2 total;
- `claude-deep` A/B x1;
- `claude-verifier` A/B x2 total;
- `codex-balanced` A/B x1;
- no-delegation/status-only A/B x1.

Only after that evidence should the candidate be converted into a permanent policy/checker change with migration coverage.

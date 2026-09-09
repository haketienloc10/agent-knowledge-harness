# Session rollover smoke

Tài liệu này kiểm tra semantic START/RESUME policy của QiQi sau khi workspace đã cài/migrate policy session rollover.

Canonical policy nằm ở `AGENTS.md`. Runtime identity/capture semantics vẫn thuộc `qiqi_delegate`; smoke này không đọc `.qiqi/state/` và không scrape native transcript.

## Preconditions

- workspace/repo setup checks hiện hành PASS;
- có một repo test an toàn mà QiQi có thể delegate investigation, implementation và verifier;
- nếu scenario dùng Work Item, current canonical state đọc được bằng bounded Work Item surface.

## Multi-phase scenario

Chạy một task có các phase sau:

1. investigation trên repo A;
2. stable reconciliation/handoff sang implementation;
3. immediate narrow fix trên cùng implementation objective;
4. independent verifier/reviewer;
5. cross-repo handoff sang repo B nếu task có downstream dependency.

Expected session behavior:

```text
investigation          -> START S1
stable handoff
implementation         -> START S2
immediate narrow fix   -> MAY RESUME S2 khi exact native continuity còn material
independent verifier   -> START S3
cross-repo handoff     -> START trong target repo
```

## Assertions

- Known `session_id` không được dùng như lý do mặc định để RESUME.
- `blocked` trước native final response vẫn giữ và RESUME exact native session.
- Preserved result-capture/infrastructure recovery key vẫn có exact-session recovery path.
- Sau stable material reconciliation boundary, next phase START fresh nếu không còn native-specific dependency.
- `claude-verifier`/independent review không inherit implementation native conversation chỉ vì cùng underlying native agent family.
- Immediate narrow continuation MAY RESUME khi context cần thiết chưa persist hoặc chưa thể safely distill.
- START/RESUME mode được chọn trước final TaskPacket referential closure; material referent không accessible dưới chosen mode phải được distill vào packet.
- Fresh child reconstruct task meaning từ current canonical state + self-sufficient TaskPacket + current repo, không dereference Work Item để đoán missing semantics.
- QiQi không đọc/poll `.qiqi/state/` để quyết định rollover.

## Failure interpretation

Nếu fresh phase thiếu material task semantics, sửa orchestration/TaskPacket closure thay vì mặc định RESUME session cũ. Nếu exact native interactive state thật sự chưa đạt stable handoff boundary, RESUME là đúng path.

Không dùng arbitrary turn/character threshold để override blocked recovery hoặc task-semantic decision trong v1.

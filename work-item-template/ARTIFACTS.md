# Work Item lifecycle documents

Các file `intake.md`, `investigation.md`, `plan.md`, `review.md`, `report.textile` là **living task documents**, không phải append-only artifacts và không phải history.

## Quy tắc chung

- Chỉ materialize file khi phase/workflow thực sự cần.
- `WORK_ITEM.md` luôn thắng nếu lifecycle document cũ mâu thuẫn current canonical task truth.
- Living document được rewrite/merge để phản ánh hiểu biết hiện tại.
- Không tạo file theo turn/session.
- Không giữ intermediate failed attempts trừ khi kết luận đó còn ngăn turn sau lặp lại một hướng sai material.
- Evidence chỉ giữ ở mức đủ support finding/acceptance/report; terminal transcript không phải artifact.

## `intake.md`

Giữ:

- Initial Request;
- effective scope/constraints/acceptance ban đầu;
- material requirement changes còn cần để giải thích current requirement.

Không giữ chronology kiểu Request 1 → Request 2 → Request 3 nếu sequence đó không còn semantic value.

## `investigation.md`

Living projection đề nghị:

```text
Scope
Verified Findings
Relevant Evidence
Open Questions
Conclusion
```

Requirement change không tự động invalidate investigation. Reconcile từng finding:

- vẫn factually valid → giữ;
- fact vẫn đúng nhưng implication đổi → giữ và reinterpret;
- phụ thuộc assumption đã supersede → revalidate hoặc bỏ;
- bị authoritative input mới contradict → replace.

## `plan.md`

Giữ current objective/approach/remaining steps/risks/verification strategy. Nếu plan đổi hướng, giữ decision cũ chỉ khi rationale còn cần để tránh quay lại hướng invalid.

## `review.md`

Đánh giá actual result theo acceptance criteria hiện tại. Không phải implementation summary. Mỗi material criterion nên có evidence + assessment rõ.

## `report.textile`

Final external deliverable được derive từ current Work Item + accepted lifecycle findings/evidence, không từ conversation memory.

Default Redmine report dùng 8 phần:

1. Root-cause/requirement
2. Solution
3. Affected
4. Impact Module Analysis
5. SQL_Report
6. Commits
7. Testcase / UT
8. Deploy

Không invent branch/commit/deploy/test result. Giữ placeholder explicit khi user phải tự điền.

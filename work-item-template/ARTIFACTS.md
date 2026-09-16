# Work Item lifecycle documents

Các file `10_intake.md`, `20_investigation.md`, `30_plan.md`, `40_review.md`, `90_report.textile` là **living task documents**, không phải append-only artifacts và không phải history.

Canonical dossier order:

```text
00_WORK_ITEM.md
10_intake.md?
20_investigation.md?
30_plan.md?
40_review.md?
references/?
90_report.textile?
```

Numeric prefixes là part of filename contract, không chỉ cosmetic sorting. Gaps `10/20/30/40/.../90` cho phép chèn future material phases mà không rename toàn bộ dossier. `references/` không đánh số vì không phải lifecycle phase.

## Quy tắc chung

- Chỉ materialize file khi phase/workflow thực sự cần.
- `00_WORK_ITEM.md` luôn thắng nếu lifecycle document cũ mâu thuẫn current canonical task truth.
- Living document được rewrite/merge để phản ánh hiểu biết hiện tại.
- Không tạo file theo turn/session.
- Không giữ intermediate failed attempts trừ khi kết luận đó còn ngăn turn sau lặp lại một hướng sai material.
- Evidence chỉ giữ ở mức đủ support finding/acceptance/report; terminal transcript không phải artifact.
- Legacy unprefixed lifecycle filenames phải được migrate, không giữ song song với numbered canonical names.

## `10_intake.md`

Giữ:

- Initial Request;
- effective scope/constraints/acceptance ban đầu;
- material requirement changes còn cần để giải thích current requirement.

Không giữ chronology kiểu Request 1 → Request 2 → Request 3 nếu sequence đó không còn semantic value.

## `20_investigation.md`

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

## `30_plan.md`

Giữ current objective/approach/remaining steps/risks/verification strategy. Nếu plan đổi hướng, giữ decision cũ chỉ khi rationale còn cần để tránh quay lại hướng invalid.

## `40_review.md`

Đánh giá actual result theo acceptance criteria hiện tại. Không phải implementation summary. Mỗi material criterion nên có evidence + assessment rõ.

## `90_report.textile`

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

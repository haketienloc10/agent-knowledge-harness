# TaskPacket referential-closure contract

## Mục đích

TaskPacket là semantic snapshot cho một delegated turn. Semantic completeness không chỉ yêu cầu đủ field; mọi reference có thể ảnh hưởng cách child hiểu assignment hoặc cách QiQi accept kết quả cũng phải **resolve được từ child-visible context mà delegation mode thực sự bảo đảm**.

Rule này áp dụng chung cho prior-turn text, media, file/attachment, bảng, log/snippet, tool result, external observation, generated artifact hoặc bất kỳ object/context nào nằm ngoài current packet.

## Invariant

> Mọi task-material referent phải được đóng trên child-visible context trước delegation.

Một referent là **task-material** nếu thay đổi hoặc mất referent đó có thể làm thay đổi ít nhất một trong:

- objective/outcome;
- scope hoặc out-of-scope;
- trusted premise hoặc claim cần investigate;
- constraint;
- acceptance condition;
- known unknown;
- mức độ/coverage của evidence dùng để match, reject hoặc kết luận.

Một câu reference không tự mang referent. Các cụm kiểu “ở trên”, “trước đó”, “file vừa gửi”, “ảnh trước”, “kết quả vừa nói”, “như đã trao đổi” hoặc tương đương chỉ hợp lệ nếu chosen delegation mode thực sự làm referent đó child-accessible và reference đủ unambiguous để resolve.

## Child-visible context

QiQi chỉ được coi một referent là child-visible khi visibility được contract/runtime bảo đảm cho delegated turn, ví dụ:

- nội dung hiện có trong TaskPacket;
- current repository và stable repo/execution policy mà child được phép đọc;
- input/artifact transport được delegation tool explicitly expose, nếu contract tương lai có surface này;
- exact native session context được runtime bảo đảm khi RESUME và referent thực sự nằm trong session đó.

Không được giả định child nhìn thấy:

- parent QiQi/user conversation;
- attachment/media chỉ tồn tại ở parent turn;
- parent-side tool output chưa được truyền;
- Work Item/Knowledge/sibling state để reconstruct missing task meaning;
- một object chỉ được mô tả bằng deictic wording nhưng không có locator/content child-accessible.

START và RESUME khác nhau về native session continuity, nhưng **parent conversation không tự trở thành child-visible context trong cả hai mode**.

## Closure algorithm trước delegation

Với candidate TaskPacket:

1. Xác định các task-material semantics hiện tại, kể cả semantics đến từ turn/artifact/tool output trước đó.
2. Tìm các reference mà meaning phụ thuộc vào referent ngoài candidate packet.
3. Với mỗi referent, xác định chosen START/RESUME mode có bảo đảm child access referent hay không.
4. Nếu **có**, identify referent đủ unambiguous và vẫn preserve material provenance/coverage trong packet khi chúng ảnh hưởng confidence hoặc acceptance.
5. Nếu **không**, distill **smallest sufficient semantics** của referent vào các TaskPacket field hiện có.
6. Preserve epistemic/coverage limitation của evidence: partial, cropped, sampled, truncated, redacted, stale, inferred/derived hoặc otherwise non-exhaustive.
7. Không dùng phần không quan sát được của partial evidence làm negative evidence. Ví dụ candidate có thêm field/record/section ngoài crop/sample không phải lý do reject nếu acceptance chỉ yêu cầu match phần quan sát.
8. Khi user cung cấp clue mới ở turn sau, compose clue mới với prior material semantics còn hiệu lực. Không để clue mới vô tình thay thế context cũ chỉ vì START một session mới.
9. Chỉ bỏ prior semantics khi chúng explicit superseded, contradicted/reconciled hoặc không còn material cho current delegated outcome.
10. Sau closure, áp dụng minimality bình thường: không forward toàn conversation/artifact nếu một semantic distillation nhỏ hơn đã đủ.

## Mapping vào TaskPacket hiện có

Referential closure **không yêu cầu một TaskPacket field mới**. Map theo semantic role:

- observed/external premise child MAY rely on → `context.trusted_facts[]` + `source`;
- proposition từ prior context nhưng cần establish → `context.claims_to_investigate[]` + `source`;
- hard boundary phát sinh từ coverage/product/system requirement → `constraints[]`;
- observable condition cần demonstrate/correlate → `acceptance_criteria[]`;
- unresolved limitation/ambiguity không được silently assume → `known_unknowns[]`;
- domain surface cần inspect/change → `scope[]`;
- adjacent work bị loại → `out_of_scope[]`.

Nếu future delegation contract có typed artifact transport, artifact có thể được truyền bằng transport đó; invariant vẫn giữ nguyên: child phải resolve được referent và material semantics/provenance/coverage không được mất.

## Coverage semantics

Evidence coverage là task semantics khi nó ảnh hưởng reasoning.

Ví dụ generic:

- screenshot crop chỉ chứng minh phần UI nhìn thấy;
- log excerpt chỉ chứng minh sampled time/range được cung cấp;
- CSV subset không chứng minh record ngoài subset không tồn tại;
- redacted document không chứng minh phần bị redacted không chứa related data;
- truncated tool output không chứng minh match không tồn tại ngoài phần bị truncate.

Do đó:

```text
absence outside observed coverage != negative evidence
```

Nếu child cần exhaustive conclusion nhưng evidence chỉ partial, packet phải preserve limitation đó để child biết cần owner-source/runtime evidence bổ sung hoặc report unresolved.

## Multi-turn composition

Task continuity không đồng nghĩa native session continuity.

Một turn sau có thể bổ sung route, identifier, URL, error code, timestamp, environment clue hoặc product decision mới. Khi clue này materially đổi hướng execution, QiQi có thể START fresh session. START là hợp lệ nếu packet mới đóng đầy đủ trên toàn bộ material semantics còn hiệu lực.

Sai:

```text
prior turn: material artifact/observation
later turn: new route clue
fresh START packet: new route clue + "đối chiếu với nội dung trước đó"
```

Đúng:

```text
prior material semantics
+ later clue
+ provenance/coverage limitations
        ↓ distill
self-sufficient TaskPacket
        ↓
START or RESUME child
```

## Không phải mục tiêu

Rule này không:

- bắt QiQi copy nguyên user conversation/history;
- yêu cầu encode binary attachment vào TaskPacket text;
- yêu cầu thêm `attachments` field vào `qiqi_delegate`;
- cấm RESUME dùng exact native session continuity được runtime bảo đảm;
- cho phép child dùng Work Item/Knowledge/sibling repo để recover omitted task meaning;
- biến syntax/deictic keyword blacklist thành correctness mechanism;
- yêu cầu child resolve product semantics từ implementation detail mà QiQi đã làm mất.

Keyword blacklist không giải quyết được invariant vì reference có thể xuất hiện ở bất kỳ ngôn ngữ/cách diễn đạt nào, và cùng một wording có thể hợp lệ hoặc không hợp lệ tùy referent có thực sự child-visible hay không.

## Regression matrix

Các evaluation/smoke case nên cover ít nhất:

1. prior-turn **text** chứa material requirement + later clue + fresh START;
2. prior-turn **media** chứa material observations + later clue + fresh START;
3. prior-turn **file/attachment** chứa scoped data/constraints + later clue;
4. parent-side **tool result** bị truncate/partial nhưng material cho assignment;
5. **external observation** có provenance/coverage limitation;
6. RESUME nơi referent thực sự nằm trong exact native session context;
7. ambiguous/dangling deictic reference không có child-visible referent;
8. clue mới additive với prior semantics thay vì silently replacing chúng;
9. explicit supersession cho phép bỏ prior semantics;
10. partial evidence không tạo false negative ngoài observed coverage.

Expected invariant cho mọi case:

```text
context-naive child không cần hidden parent state để hiểu task meaning
```

và packet vẫn giữ `smallest sufficient`: closure truyền semantic meaning cần thiết, không duplicate toàn history.

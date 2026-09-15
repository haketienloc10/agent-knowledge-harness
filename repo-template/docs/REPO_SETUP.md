# Repository setup

Repo child nhận TaskPacket qua `qiqi_delegate` và có thể đọc shared Work Item directory cho tracked task.

## Boundary

- current Git root là implementation scope;
- `$QIQI_WORK_ITEMS_DIR` là authorized read-only task context khi TaskPacket có Work Item locator;
- sibling repos và `.qiqi/state` không được đọc/sửa;
- child trả evidence bằng native response, QiQi reconcile canonical Work Item.

TaskPacket vẫn phải đủ objective/scope/acceptance; Work Item không bù cho packet thiếu nghĩa.

## Verification

```bash
bash scripts/repo-check.sh
```

Smoke expectation:

1. tracked delegation có locator `work_item=<id>; revision=<n>`;
2. child đọc được mounted Work Item khi cần;
3. child không mutate Work Item;
4. final response report material evidence/verification để QiQi reconcile;
5. no per-turn Work Item history artifact được tạo.

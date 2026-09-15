# Repository setup

Repo child nhận TaskPacket qua `qiqi_delegate` và có thể đọc shared Work Item directory cho tracked task.

## Boundary

- current Git root là implementation scope;
- tracked Work Item được cấp bằng absolute `work_item_path=<absolute-path>; id=<canonical-id>; revision=<n>` và chỉ read-only;
- child không phụ thuộc vào `$QIQI_WORK_ITEMS_DIR` inheritance để tìm dossier;
- sibling repos và `.qiqi/state` không được đọc/sửa;
- child trả material evidence bằng native response, QiQi reconcile canonical Work Item;
- secret/credential/token/private-customer/raw sensitive evidence phải redact khỏi native response và Shared Knowledge.

TaskPacket vẫn phải đủ objective/scope/acceptance; Work Item không bù cho packet thiếu nghĩa.

## Verification

```bash
bash scripts/repo-check.sh
```

Smoke expectation:

1. tracked delegation có absolute Work Item path + canonical id + revision;
2. child đọc được mounted Work Item khi cần;
3. child không mutate Work Item;
4. final response report material evidence/verification nhưng không persist secret/sensitive raw values;
5. no per-turn Work Item history artifact được tạo.

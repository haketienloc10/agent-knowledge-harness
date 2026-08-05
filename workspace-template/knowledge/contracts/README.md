# Cross-repository Contracts

Thư mục này ghi contract được producer và consumer cùng phụ thuộc: API, event,
schema, file format hoặc field truyền giữa các repository.

Mỗi tài liệu nên có cấu trúc:

```markdown
---
id: contract-<name>
status: verified
owner: <producer-repository>
consumers:
  - <consumer-repository>
updated: YYYY-MM-DD
---

# <Tên contract>

## Mục đích và phạm vi

## Producer và consumers

## Shape hoặc behavior bắt buộc

## Compatibility rule

## Failure và fallback

## Verification

## Source of truth
```

`Source of truth` phải trỏ đến spec, code, schema hoặc test chính thức. Tài liệu
workspace chỉ tóm tắt phần cần để các repo phối hợp; không sao chép toàn bộ định
nghĩa từ owner repository.

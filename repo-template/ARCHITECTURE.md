# Architecture

Tài liệu này mô tả kiến trúc **nội bộ** của repository. Quan hệ tổng thể giữa
nhiều repository thuộc `SYSTEM_MAP.md` tại workspace và không được sao chép đầy
đủ vào đây.

## Repository responsibility

- Sở hữu: `{{OWNED_RESPONSIBILITIES}}`
- Không sở hữu: `{{NON_OWNED_RESPONSIBILITIES}}`

## Entrypoints

| Entrypoint | Vai trò | Source |
|---|---|---|
| `{{ENTRYPOINT}}` | `{{ENTRYPOINT_ROLE}}` | `{{ENTRYPOINT_SOURCE}}` |

## Module map

| Module | Trách nhiệm | Phụ thuộc nội bộ |
|---|---|---|
| `{{MODULE}}` | `{{MODULE_RESPONSIBILITY}}` | `{{INTERNAL_DEPENDENCIES}}` |

## Internal data flow

Mô tả luồng chính bên trong repo bằng các bước ngắn và liên kết đến source có
thể kiểm tra.

```text
{{INTERNAL_DATA_FLOW}}
```

## External boundaries

Chỉ mô tả phần boundary mà repo này trực tiếp sở hữu hoặc tiêu thụ. Chi tiết
cross-repo đầy đủ thuộc workspace knowledge.

| Boundary | Direction | Contract owner | Local source |
|---|---|---|---|
| `{{BOUNDARY}}` | `inbound | outbound` | `{{CONTRACT_OWNER}}` | `{{LOCAL_SOURCE}}` |

## Data ownership

| Dữ liệu hoặc resource | Owner | Cách repo này truy cập |
|---|---|---|
| `{{RESOURCE}}` | `{{OWNER}}` | `{{ACCESS_PATH}}` |

## Constraints

- `{{ARCHITECTURAL_CONSTRAINT}}`

## Evidence

- `{{SOURCE_OR_COMMAND}}`

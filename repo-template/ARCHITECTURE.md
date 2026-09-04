# Architecture

Tài liệu này mô tả **live architecture nội bộ** của repository. Repository registry và
dependency topology cơ bản thuộc workspace `repos.yaml`; cross-repo contracts, ownership
boundaries và integration semantics thuộc workspace `SYSTEM_MAP.md`. Durable reusable
conclusion được distill qua Shared Knowledge MCP; không copy Shared Knowledge Store
vào file này.

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

Mô tả luồng chính bên trong repo bằng các bước ngắn và liên kết đến source có thể
kiểm tra.

```text
{{INTERNAL_DATA_FLOW}}
```

## External boundaries

Chỉ mô tả phần boundary mà repo này trực tiếp sở hữu hoặc tiêu thụ. Registry/dependency
basics của toàn workspace thuộc `repos.yaml`; live cross-repo contract/ownership/integration
semantics thuộc `SYSTEM_MAP.md`. Reusable distilled context có thể nằm trong Shared
Knowledge Store.

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

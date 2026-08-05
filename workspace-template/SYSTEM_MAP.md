# System Map

Tệp này mô tả quan hệ giữa các Git repository trong local workspace. Nó không
thay thế `ARCHITECTURE.md` hoặc artifact tương ứng của từng repository.

## Hình dạng Hệ thống

- Sản phẩm: `{{PRODUCT_NAME}}`
- Local workspace root: `{{WORKSPACE_ROOT}}`
- Hạ tầng dùng chung: `{{SHARED_INFRASTRUCTURE}}`
- Command integration chính: `{{INTEGRATION_COMMAND}}`

## Danh sách Repository

| Repository | Vai trò | Git root | Runtime/entrypoint | Phụ thuộc |
|---|---|---|---|---|
| `{{MODULE_1}}` | `{{MODULE_1_ROLE}}` | `{{MODULE_1_PATH}}` | `{{MODULE_1_ENTRYPOINT}}` | `{{MODULE_1_DEPENDENCIES}}` |
| `{{MODULE_2}}` | `{{MODULE_2_ROLE}}` | `{{MODULE_2_PATH}}` | `{{MODULE_2_ENTRYPOINT}}` | `{{MODULE_2_DEPENDENCIES}}` |

Danh sách phải khớp với `repos.yaml`. Không đưa hạ tầng không phải Git
repository vào registry.

## Thứ tự Khởi động Local

1. `{{INFRASTRUCTURE_STEP}}`
2. `{{PRODUCER_OR_FOUNDATION_MODULE}}`
3. `{{DEPENDENT_MODULE}}`
4. `{{FRONTEND_OR_EDGE_MODULE}}`

## Contract Liên Repository

| Contract | Producer | Consumers | Kiểu | Compatibility rule | Source of truth |
|---|---|---|---|---|---|
| `{{CONTRACT_NAME}}` | `{{PRODUCER}}` | `{{CONSUMERS}}` | `HTTP / event / schema` | `{{COMPATIBILITY_RULE}}` | `{{SPEC_OR_CODE_PATH}}` |

Chi tiết contract có khả năng dùng lại có thể được chắt lọc vào
`knowledge/contracts/`, nhưng bảng này vẫn giữ bản đồ producer–consumer và liên
kết đến source of truth.

## Ranh giới Dữ liệu và Ownership

| Dữ liệu hoặc resource | Owner | Consumer được phép | Cách truy cập |
|---|---|---|---|
| `{{RESOURCE}}` | `{{OWNER_MODULE}}` | `{{ALLOWED_CONSUMERS}}` | `{{API_EVENT_OR_READ_MODEL}}` |

Không truy cập trực tiếp database, bảng, queue hoặc internal endpoint của repo
khác trừ khi bảng này cho phép rõ ràng.

## Kiểm thử Integration

| Kiểm tra | Repository liên quan | Command | Điều kiện trước khi chạy |
|---|---|---|---|
| `{{SMOKE_OR_CONTRACT_CHECK}}` | `{{AFFECTED_MODULES}}` | `{{COMMAND}}` | `{{DEPENDENCIES}}` |

## Thay đổi Breaking và Rollback

- Owner của contract: `{{CONTRACT_OWNER_OR_TEAM}}`
- Quy trình deprecation: `{{DEPRECATION_POLICY}}`
- Điều kiện xóa contract cũ: `{{REMOVAL_CONDITION}}`
- Rollback: `{{ROLLBACK_APPROACH}}`

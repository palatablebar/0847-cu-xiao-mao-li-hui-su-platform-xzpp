# 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `sku` | text | 主键 |
| `line_qty` | int_positive | 业务字段 |
| `list_price_cents` | int | 业务字段 |
| `sell_price_cents` | int | 业务字段 |
| `supplier_fund_cents` | int | 业务字段 |
| `coupon_cents` | int | 业务字段 |
| `unit_cost_cents` | int | 业务字段 |

空字符串、`-`、`NA`、`null` 和 `未提供` 按空值处理。金额字段在整理层转为整数分或整数最小单位；日期按 ISO 日期解析；带时间的字段按本地时间解析。标识字段保持为文本，前导零不会被去除。

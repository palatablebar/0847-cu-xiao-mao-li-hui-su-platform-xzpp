# 接口

- `GET /`：工作台。
- `GET /api/catalog`：阶段、字段和样例。
- `POST /api/stages/{stage}`：按阶段返回处理结果。
- `POST /api/runs`：执行完整批次并保存草稿。
- `GET /api/runs/{id}`：读取批次。
- `POST /api/runs/{id}/review`：签发或暂缓，提交 `decision`、`comment`、`expected_revision`。
- `GET /api/runs/{id}/evidence`：下载已签发证据。
- `GET /api/examples/{profile}`：下载样例。
- `GET /healthz`：健康检查。

## 活动券额度

- `POST /api/campaigns`：创建活动，提交 `name`、`quota_cents`。
- `GET /api/campaigns`：列出活动及额度摘要。
- `GET /api/campaigns/{id}`：活动详情，含订单有效状态与额度占用。
- `POST /api/campaigns/{id}/orders`：提交订单，提交 `order_id`、`received_at`、`line_qty`、`sell_price_cents`、`unit_cost_cents`、`supplier_fund_cents`、`coupon_cents`。同一订单号重复提交须内容一致（幂等），否则返回 `ORDER_CONFLICT`。
- `POST /api/campaigns/{id}/orders/{order_id}/issue`：签发；额度不足返回 `QUOTA_UNAVAILABLE`，亏损返回 `ORDER_LOSS`，已取消返回 `ORDER_CANCELLED`。重复签发幂等。
- `POST /api/campaigns/{id}/orders/{order_id}/cancel`：取消并释放额度；重复取消幂等。
- `GET /api/campaigns/{id}/orders/{order_id}/ship`：发货查询，返回 `can_ship`、`can_issue`、`status`、`reason`、`waitlist_position` 等。

订单状态：`DRAFT`（已占额度待签发）、`ISSUED`（已签发）、`WAITLIST`（候补）、`EXCLUDED`（用券亏损不占额度）、`CANCELLED`（已取消）。

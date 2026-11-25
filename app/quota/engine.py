"""券额度分配引擎。

规则（与 docs/BUSINESS-RULES.md 对应）：

* 同一活动的订单共用一份券额度。
* 未签发的订单按接单时间优先用券；接单时间相同按提交顺序（seq）决胜。
* 已签发订单的承诺不可撤销：即使被补进的更早订单挤掉额度，仍然发货并兑现券。
* 用券后会亏损的订单不占额度，也不能签发/发货。
* 额度不足以支付整张券时该订单候补，不做部分发放。
* 订单取消后其占用额度释放，候补按接单时间顺序接用。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

DRAFT = "DRAFT"
ISSUED = "ISSUED"
CANCELLED = "CANCELLED"

# 对外展示的有效状态：DRAFT（已占额度、待签发）/ WAITLIST（候补）等。
WAITLIST = "WAITLIST"
EXCLUDED = "EXCLUDED"

REASON_PROMISED = "PROMISED"
REASON_PROMISED_PREEMPTED = "PROMISED_PREEMPTED"
REASON_NOT_ISSUED = "NOT_ISSUED"
REASON_WAITLIST = "QUOTA_INSUFFICIENT"
REASON_LOSS = "COUPON_CAUSES_LOSS"
REASON_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Order:
    order_id: str
    seq: int
    received_us: int
    received_at: str
    coupon_cents: int
    line_qty: int
    sell_price_cents: int
    unit_cost_cents: int
    supplier_fund_cents: int
    state: str = DRAFT


def margin_with_coupon(order: Order) -> int:
    """用券后的行毛利（整数分）。

    收入 = 售价 × 数量 − 券；成本 = 单件成本 × 数量 − 供应商出资；
    两项各自在整理层封顶（券不超过收入、出资不超过成本），此处只做整数运算。
    """
    revenue = order.sell_price_cents * order.line_qty - order.coupon_cents
    cost = order.unit_cost_cents * order.line_qty - order.supplier_fund_cents
    return revenue - cost


def margin_rate_with_coupon(order: Order) -> Decimal:
    revenue = order.sell_price_cents * order.line_qty - order.coupon_cents
    if revenue == 0:
        return Decimal("0")
    return Decimal(margin_with_coupon(order)) / Decimal(revenue)


def is_loss(order: Order) -> bool:
    return margin_with_coupon(order) < 0


def _grant_plan(quota_cents: int, orders):
    """按 (接单时间, seq) 贪心分配额度。返回 {order_id: 是否占用额度}。"""
    remaining = max(0, int(quota_cents))
    granted = {}
    for order in sorted(orders, key=lambda item: (item.received_us, item.seq)):
        if order.state == CANCELLED or is_loss(order):
            continue
        if order.coupon_cents <= remaining:
            granted[order.order_id] = True
            remaining -= order.coupon_cents
        else:
            granted[order.order_id] = False
    return granted


def evaluate(quota_cents: int, orders) -> dict:
    """计算活动视图：各订单有效状态、发货结论与额度占用。"""
    ordered = sorted(orders, key=lambda item: (item.received_us, item.seq))
    granted = _grant_plan(quota_cents, ordered)

    waitlist_position = 0
    views = []
    by_id = {}
    for order in ordered:
        loss = is_loss(order)
        if order.state == CANCELLED:
            status, reason = CANCELLED, REASON_CANCELLED
        elif loss:
            # 用券即亏损：不占额度；已签发的承诺仍按原样兑现。
            status = ISSUED if order.state == ISSUED else EXCLUDED
            reason = REASON_PROMISED if order.state == ISSUED else REASON_LOSS
        elif order.state == ISSUED:
            status = ISSUED
            reason = REASON_PROMISED if granted.get(order.order_id) else REASON_PROMISED_PREEMPTED
        elif granted.get(order.order_id):
            status, reason = DRAFT, REASON_NOT_ISSUED
        else:
            status, reason = WAITLIST, REASON_WAITLIST

        position = None
        if status == WAITLIST:
            waitlist_position += 1
            position = waitlist_position

        view = {
            "order_id": order.order_id,
            "seq": order.seq,
            "received_at": order.received_at,
            "coupon_cents": order.coupon_cents,
            "line_qty": order.line_qty,
            "sell_price_cents": order.sell_price_cents,
            "unit_cost_cents": order.unit_cost_cents,
            "supplier_fund_cents": order.supplier_fund_cents,
            "margin_with_coupon": margin_with_coupon(order),
            "margin_rate_with_coupon": str(margin_rate_with_coupon(order)),
            "state": order.state,
            "status": status,
            "reason": reason,
            "quota_granted": bool(granted.get(order.order_id, False)),
            "preempted": status == ISSUED and not granted.get(order.order_id, False) and not loss,
            "can_ship": status == ISSUED,
            "can_issue": status == DRAFT,
            "waitlist_position": position,
        }
        views.append(view)
        by_id[order.order_id] = view

    reserved = sum(item["coupon_cents"] for item in views if item["quota_granted"])
    committed = sum(item["coupon_cents"] for item in views if item["state"] == ISSUED)
    preempted_cents = sum(item["coupon_cents"] for item in views if item["preempted"])
    exposure = reserved + preempted_cents
    counts = {"issued": 0, "draft": 0, "waitlist": 0, "excluded": 0, "cancelled": 0}
    for item in views:
        key = {ISSUED: "issued", DRAFT: "draft", WAITLIST: "waitlist",
               EXCLUDED: "excluded", CANCELLED: "cancelled"}[item["status"]]
        counts[key] += 1
    usage = {
        "quota_cents": int(quota_cents),
        "reserved_cents": reserved,
        "available_cents": max(0, int(quota_cents) - reserved),
        "committed_cents": committed,
        "preempted_cents": preempted_cents,
        "exposure_cents": exposure,
        "overcommitted_cents": max(0, exposure - int(quota_cents)),
    }
    return {"orders": views, "by_id": by_id, "usage": usage, "counts": counts}

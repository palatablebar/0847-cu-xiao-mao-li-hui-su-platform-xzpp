from decimal import Decimal

from app.quota.engine import (
    CANCELLED,
    DRAFT,
    EXCLUDED,
    ISSUED,
    WAITLIST,
    Order,
    evaluate,
    is_loss,
    margin_with_coupon,
)


def order(order_id, seq, received_us, coupon, qty=1, sell=1000, cost=300, fund=0, state=DRAFT):
    return Order(order_id=order_id, seq=seq, received_us=received_us, received_at=f"t{received_us}",
                 coupon_cents=coupon, line_qty=qty, sell_price_cents=sell,
                 unit_cost_cents=cost, supplier_fund_cents=fund, state=state)


def statuses(view):
    return {item["order_id"]: item["status"] for item in view["orders"]}


def test_margin_uses_coupon_after_supplier_fund():
    item = order("A", 1, 100, 500, qty=10, sell=900, cost=600, fund=1000)
    # revenue 9000-500=8500; cost 6000-1000=5000; margin 3500
    assert margin_with_coupon(item) == 3500


def test_drafts_use_quota_by_receipt_time():
    view = evaluate(1000, [order("late", 1, 200, 600), order("early", 2, 100, 600)])
    assert statuses(view) == {"late": WAITLIST, "early": DRAFT}
    assert view["usage"]["reserved_cents"] == 600
    assert view["usage"]["available_cents"] == 400


def test_partial_quota_goes_to_waitlist():
    view = evaluate(500, [order("A", 1, 100, 600)])
    assert statuses(view) == {"A": WAITLIST}
    assert view["orders"][0]["waitlist_position"] == 1
    assert view["usage"]["reserved_cents"] == 0


def test_loss_order_never_reserves_quota():
    lossy = order("L", 1, 100, 900, qty=1, sell=1000, cost=600)
    assert is_loss(lossy)
    view = evaluate(1000, [lossy, order("B", 2, 200, 600, qty=1, sell=1000, cost=300)])
    assert statuses(view)["L"] == EXCLUDED
    assert statuses(view)["B"] == DRAFT
    assert view["usage"]["reserved_cents"] == 600


def test_earlier_draft_preempts_issued_order_but_promise_holds():
    issued = order("late", 1, 200, 600, state=ISSUED)
    view = evaluate(1000, [issued, order("early", 2, 100, 600)])
    assert statuses(view) == {"late": ISSUED, "early": DRAFT}
    late = view["by_id"]["late"]
    assert late["preempted"] is True
    assert late["can_ship"] is True
    assert late["quota_granted"] is False
    assert view["usage"]["reserved_cents"] == 600
    assert view["usage"]["preempted_cents"] == 600
    assert view["usage"]["exposure_cents"] == 1200
    assert view["usage"]["overcommitted_cents"] == 200


def test_issued_order_keeps_quota_when_not_preempted():
    view = evaluate(1000, [order("A", 1, 100, 600, state=ISSUED), order("B", 2, 200, 600)])
    assert statuses(view) == {"A": ISSUED, "B": WAITLIST}
    assert view["by_id"]["A"]["preempted"] is False
    assert view["usage"]["overcommitted_cents"] == 0


def test_equal_receipt_time_breaks_tie_by_seq():
    view = evaluate(600, [order("first", 1, 100, 600), order("second", 2, 100, 600)])
    assert statuses(view) == {"first": DRAFT, "second": WAITLIST}
    assert view["by_id"]["second"]["waitlist_position"] == 1


def test_cancelled_order_releases_quota_to_waitlist():
    view = evaluate(600, [order("gone", 1, 100, 600, state=CANCELLED), order("next", 2, 200, 600)])
    assert statuses(view) == {"gone": CANCELLED, "next": DRAFT}
    assert view["usage"]["reserved_cents"] == 600


def test_margin_rate_is_decimal():
    view = evaluate(1000, [order("A", 1, 100, 500)])
    assert Decimal(view["by_id"]["A"]["margin_rate_with_coupon"]) == Decimal("0.4")


def test_usage_counts():
    view = evaluate(1000, [order("A", 1, 100, 600), order("B", 2, 200, 600), order("L", 3, 300, 900)])
    assert view["counts"] == {"issued": 0, "draft": 1, "waitlist": 1, "excluded": 1, "cancelled": 0}

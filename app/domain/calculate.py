from datetime import date, timedelta
from app.catalog import SPEC
from app.domain.helpers import *  # noqa: F401,F403


def calculate_rows(items):
    out = []
    rows = items
    for item in items:
        revenue = item["sell_price_cents"] * item["line_qty"] - item["coupon_cents"]
        cost = item["unit_cost_cents"] * item["line_qty"] - item["supplier_fund_cents"]
        margin = revenue - cost
        item["net_revenue"] = revenue
        item["net_cost"] = cost
        item["margin"] = margin
        item["margin_rate"] = D(str(margin), "CALC") / D(str(revenue), "CALC") if revenue else D("0", "CALC")
        item["metric"] = D(str(margin), "CALC")
        item["limit"] = D(str(revenue), "LIMIT")
        out.append(item)
    for item in out:
        item.setdefault("label", str(item.get(SPEC["key"], "")))
    return out

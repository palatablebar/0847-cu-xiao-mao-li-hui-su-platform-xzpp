from app.domain.helpers import D


def decide_rows(items):
    for item in items:
        if item["margin"] < 0:
            item["verdict"] = "REJECT"
            item["reason"] = "NEGATIVE_MARGIN"
        elif item["margin_rate"] < D("0.20", "LIMIT"):
            item["verdict"] = "REVIEW"
            item["reason"] = "MARGIN_BELOW_20"
        else:
            item["verdict"] = "PASS"
            item["reason"] = "MARGIN_OK"
        item.setdefault("verdict", "PASS")
        item.setdefault("reason", "OK")
    return items

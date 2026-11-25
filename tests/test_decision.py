from app.domain.decision import decide_rows
from tests.domain_cases import calc, run, run_profile


def test_clean_sample_has_no_blocker():
    results, _ = run_profile("clean")
    assert sum(1 for item in results if item["verdict"] == "REJECT") == 0


def test_dirty_sample_has_blocker():
    results, _ = run_profile("dirty")
    assert any(item["verdict"] == "REJECT" for item in results)


def test_each_result_has_reason():
    results, _ = run_profile("dirty")
    assert all(item.get("reason") for item in results)


def test_boundary_case_one():
    results, issues = run([{'sku': 'Y1', 'line_qty': '1', 'list_price_cents': '1000', 'sell_price_cents': '1000', 'supplier_fund_cents': '0', 'coupon_cents': '0', 'unit_cost_cents': '600'}])
    assert not issues
    assert results[0]["verdict"] == "PASS"
    assert results[0]["reason"] == "MARGIN_OK"


def test_boundary_case_two():
    results, issues = run([{'sku': 'Y2', 'line_qty': '1', 'list_price_cents': '1000', 'sell_price_cents': '1000', 'supplier_fund_cents': '0', 'coupon_cents': '0', 'unit_cost_cents': '900'}])
    assert not issues
    assert results[0]["verdict"] == "REVIEW"


def test_verdict_counts_match_rows():
    from app.service import pipeline
    payload = pipeline("clean")
    assert sum(payload["summary"].values()) == payload["counts"]["computed"]
    assert set(payload["summary"]) == {"PASS", "REVIEW", "REJECT"}

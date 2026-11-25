import threading

import pytest

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path / "workbench.sqlite3"))
    app.config.update(TESTING=True)
    return app.test_client()


def campaign(client, quota=1000, name="双十一"):
    response = client.post("/api/campaigns", json={"name": name, "quota_cents": quota})
    assert response.status_code == 200
    return response.get_json()["id"]


def submit(client, campaign_id, order_id, received_at="2026-11-01 09:00:00", coupon=600,
           qty=1, sell=1000, cost=300):
    response = client.post(f"/api/campaigns/{campaign_id}/orders", json={
        "order_id": order_id, "received_at": received_at, "coupon_cents": coupon,
        "line_qty": qty, "sell_price_cents": sell, "unit_cost_cents": cost, "supplier_fund_cents": 0,
    })
    assert response.status_code == 200, response.get_json()
    return response.get_json()["campaign"]


def status_of(payload, order_id):
    return next(item for item in payload["orders"] if item["order_id"] == order_id)


def test_create_and_list_campaign(client):
    campaign_id = campaign(client, quota=5000)
    listing = client.get("/api/campaigns").get_json()["campaigns"]
    assert listing[0]["id"] == campaign_id
    assert listing[0]["quota_cents"] == 5000


def test_unknown_campaign_is_404(client):
    assert client.get("/api/campaigns/nope").status_code == 404


def test_order_uses_shared_quota_by_receipt_time(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "late", received_at="2026-11-01 10:00:00")
    payload = submit(client, campaign_id, "early", received_at="2026-11-01 08:00:00")
    assert status_of(payload, "early")["status"] == "DRAFT"
    assert status_of(payload, "late")["status"] == "WAITLIST"
    assert payload["usage"]["reserved_cents"] == 600
    assert payload["usage"]["available_cents"] == 400


def test_waitlist_waits_for_full_amount(client):
    campaign_id = campaign(client, quota=500)
    payload = submit(client, campaign_id, "A", coupon=600)
    order = status_of(payload, "A")
    assert order["status"] == "WAITLIST"
    assert order["waitlist_position"] == 1
    assert payload["usage"]["reserved_cents"] == 0


def test_issue_then_ship_query(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A")
    before = client.get(f"/api/campaigns/{campaign_id}/orders/A/ship").get_json()
    assert before["can_ship"] is False and before["can_issue"] is True
    payload = client.post(f"/api/campaigns/{campaign_id}/orders/A/issue").get_json()["campaign"]
    assert status_of(payload, "A")["status"] == "ISSUED"
    after = client.get(f"/api/campaigns/{campaign_id}/orders/A/ship").get_json()
    assert after["can_ship"] is True


def test_loss_order_cannot_issue_or_ship(client):
    campaign_id = campaign(client, quota=5000)
    payload = submit(client, campaign_id, "L", coupon=900, sell=1000, cost=600)
    assert status_of(payload, "L")["status"] == "EXCLUDED"
    assert payload["usage"]["reserved_cents"] == 0
    response = client.post(f"/api/campaigns/{campaign_id}/orders/L/issue")
    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_LOSS"


def test_earlier_backfill_preempts_issued_but_still_ships(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "late", received_at="2026-11-01 10:00:00")
    client.post(f"/api/campaigns/{campaign_id}/orders/late/issue")
    payload = submit(client, campaign_id, "early", received_at="2026-11-01 08:00:00")
    late = status_of(payload, "late")
    early = status_of(payload, "early")
    assert late["status"] == "ISSUED" and late["can_ship"] is True
    assert late["preempted"] is True
    assert early["status"] == "DRAFT"
    assert payload["usage"]["preempted_cents"] == 600
    assert payload["usage"]["overcommitted_cents"] == 200


def test_issuing_waitlisted_order_is_rejected(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "first", received_at="2026-11-01 08:00:00")
    submit(client, campaign_id, "second", received_at="2026-11-01 09:00:00")
    response = client.post(f"/api/campaigns/{campaign_id}/orders/second/issue")
    assert response.status_code == 409
    assert response.get_json()["code"] == "QUOTA_UNAVAILABLE"


def test_cancel_releases_quota_to_waitlist(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "held", received_at="2026-11-01 08:00:00")
    submit(client, campaign_id, "waiting", received_at="2026-11-01 09:00:00")
    payload = client.post(f"/api/campaigns/{campaign_id}/orders/held/cancel").get_json()["campaign"]
    assert status_of(payload, "held")["status"] == "CANCELLED"
    assert status_of(payload, "waiting")["status"] == "DRAFT"
    assert payload["usage"]["reserved_cents"] == 600


def test_cancel_is_idempotent_and_does_not_double_release(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A", received_at="2026-11-01 08:00:00")
    submit(client, campaign_id, "B", received_at="2026-11-01 09:00:00")
    first = client.post(f"/api/campaigns/{campaign_id}/orders/A/cancel").get_json()["campaign"]
    second = client.post(f"/api/campaigns/{campaign_id}/orders/A/cancel").get_json()["campaign"]
    assert first["usage"] == second["usage"]
    assert second["usage"]["reserved_cents"] == 600


def test_issue_is_idempotent(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A")
    client.post(f"/api/campaigns/{campaign_id}/orders/A/issue")
    again = client.post(f"/api/campaigns/{campaign_id}/orders/A/issue").get_json()["campaign"]
    assert status_of(again, "A")["status"] == "ISSUED"
    assert again["usage"]["committed_cents"] == 600


def test_submitting_same_order_twice_is_idempotent(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A")
    payload = submit(client, campaign_id, "A")
    assert len(payload["orders"]) == 1


def test_resubmit_without_time_is_idempotent(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A")
    response = client.post(f"/api/campaigns/{campaign_id}/orders", json={
        "order_id": "A", "coupon_cents": 600, "line_qty": 1,
        "sell_price_cents": 1000, "unit_cost_cents": 300, "supplier_fund_cents": 0,
    })
    assert response.status_code == 200
    assert len(response.get_json()["campaign"]["orders"]) == 1


def test_conflicting_resubmit_is_rejected(client):
    campaign_id = campaign(client, quota=1000)
    submit(client, campaign_id, "A", coupon=600)
    response = client.post(f"/api/campaigns/{campaign_id}/orders", json={
        "order_id": "A", "received_at": "2026-11-01 09:00:00", "coupon_cents": 700,
        "line_qty": 1, "sell_price_cents": 1000, "unit_cost_cents": 300, "supplier_fund_cents": 0,
    })
    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_CONFLICT"


def test_invalid_coupon_over_revenue_rejected(client):
    campaign_id = campaign(client, quota=5000)
    response = client.post(f"/api/campaigns/{campaign_id}/orders", json={
        "order_id": "X", "coupon_cents": 5000, "line_qty": 1,
        "sell_price_cents": 1000, "unit_cost_cents": 300, "supplier_fund_cents": 0,
    })
    assert response.status_code == 400
    assert response.get_json()["code"] == "COUPON_OVER_REVENUE"


def test_simultaneous_submits_issue_only_one(tmp_path):
    path = str(tmp_path / "workbench.sqlite3")
    app = create_app(path)
    campaign_id = app.test_client().post("/api/campaigns", json={"name": "并发", "quota_cents": 1000}).get_json()["id"]
    barrier = threading.Barrier(2)
    results = {}

    def worker(order_id, received_at):
        local = create_app(path).test_client()
        barrier.wait()
        response = local.post(f"/api/campaigns/{campaign_id}/orders", json={
            "order_id": order_id, "received_at": received_at, "coupon_cents": 600,
            "line_qty": 1, "sell_price_cents": 1000, "unit_cost_cents": 300, "supplier_fund_cents": 0,
        })
        results[order_id] = response

    threads = [threading.Thread(target=worker, args=("A", "2026-11-01 09:00:00")),
               threading.Thread(target=worker, args=("B", "2026-11-01 09:00:01"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(response.status_code == 200 for response in results.values())
    final = app.test_client().get(f"/api/campaigns/{campaign_id}").get_json()
    shipping = [item for item in final["orders"] if item["status"] == "DRAFT"]
    waiting = [item for item in final["orders"] if item["status"] == "WAITLIST"]
    assert len(shipping) == 1
    assert len(waiting) == 1
    assert final["usage"]["reserved_cents"] == 600

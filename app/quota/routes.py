from flask import Blueprint, jsonify, request

from app.errors import DomainIssue
from app.quota.store import parse_int

quota_api = Blueprint("quota_api", __name__)


def store():
    from flask import current_app
    return current_app.extensions["quota"]


@quota_api.post("/api/campaigns")
def create_campaign():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        raise DomainIssue("BAD_REQUEST", detail="活动名称不能为空")
    quota_cents = parse_int(data.get("quota_cents"), "INVALID_QUOTA_CENTS")
    if quota_cents < 0:
        raise DomainIssue("INVALID_QUOTA_CENTS")
    return jsonify(store().create_campaign(name, quota_cents))


@quota_api.get("/api/campaigns")
def list_campaigns():
    return jsonify(campaigns=store().list_campaigns())


@quota_api.get("/api/campaigns/<campaign_id>")
def get_campaign(campaign_id):
    campaign = store().get_campaign(campaign_id)
    if campaign is None:
        raise DomainIssue("CAMPAIGN_NOT_FOUND", 404)
    return jsonify(campaign)


@quota_api.post("/api/campaigns/<campaign_id>/orders")
def submit_order(campaign_id):
    data = request.get_json(silent=True) or {}
    campaign, order_id = store().submit_order(campaign_id, data)
    return jsonify(campaign=campaign, order_id=order_id)


@quota_api.post("/api/campaigns/<campaign_id>/orders/<order_id>/issue")
def issue_order(campaign_id, order_id):
    campaign, order_id = store().issue_order(campaign_id, order_id)
    return jsonify(campaign=campaign, order_id=order_id)


@quota_api.post("/api/campaigns/<campaign_id>/orders/<order_id>/cancel")
def cancel_order(campaign_id, order_id):
    campaign, order_id = store().cancel_order(campaign_id, order_id)
    return jsonify(campaign=campaign, order_id=order_id)


@quota_api.get("/api/campaigns/<campaign_id>/orders/<order_id>/ship")
def ship_status(campaign_id, order_id):
    return jsonify(store().ship_status(campaign_id, order_id))

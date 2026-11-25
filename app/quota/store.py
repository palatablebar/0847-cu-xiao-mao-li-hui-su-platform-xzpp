"""活动券额度的持久化与并发安全操作。

所有改变分配结果的操作（提交、签发、取消）都在 ``BEGIN IMMEDIATE`` 事务中
重新读取订单并重算分配，避免并发提交时两单同时占用同一份额度。
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.errors import DomainIssue
from app.quota.engine import (
    CANCELLED,
    DRAFT,
    ISSUED,
    Order,
    evaluate,
)


FIELDS = ("line_qty", "sell_price_cents", "unit_cost_cents", "supplier_fund_cents", "coupon_cents")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_int(value, code, default=None):
    if value is None or value == "":
        if default is not None:
            return default
        raise DomainIssue(code)
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise DomainIssue(code)
    if number != number.to_integral_value():
        raise DomainIssue(code)
    return int(number)


def parse_received(value):
    """解析接单时间，返回 (显示文本, 微秒整数值)。缺省用当前时间。"""
    if value is None or str(value).strip() == "":
        moment = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        text = str(value).strip().replace("T", " ")
        moment = None
        for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                moment = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        if moment is None:
            raise DomainIssue("BAD_RECEIVED_AT")
    micros = int((moment - datetime(1970, 1, 1)).total_seconds() * 1_000_000)
    return moment.isoformat(sep=" "), micros


class QuotaStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def init(self):
        with self.connect() as db:
            db.executescript(
                '''
                CREATE TABLE IF NOT EXISTS campaigns(
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  quota_cents INTEGER NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaign_orders(
                  campaign_id TEXT NOT NULL,
                  id TEXT NOT NULL,
                  seq INTEGER NOT NULL,
                  received_at TEXT NOT NULL,
                  received_us INTEGER NOT NULL,
                  line_qty INTEGER NOT NULL,
                  sell_price_cents INTEGER NOT NULL,
                  unit_cost_cents INTEGER NOT NULL,
                  supplier_fund_cents INTEGER NOT NULL,
                  coupon_cents INTEGER NOT NULL,
                  state TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY(campaign_id, id)
                );
                CREATE INDEX IF NOT EXISTS idx_orders_campaign
                  ON campaign_orders(campaign_id, received_us, seq);
                '''
            )

    # ---- campaigns -------------------------------------------------
    def create_campaign(self, name, quota_cents):
        campaign_id = uuid.uuid4().hex[:12]
        with self.transaction() as db:
            db.execute(
                "INSERT INTO campaigns(id,name,quota_cents,created_at) VALUES(?,?,?,?)",
                (campaign_id, name, quota_cents, _now()),
            )
        return self.get_campaign(campaign_id)

    def get_campaign_row(self, campaign_id, db=None):
        owned = db is None
        if owned:
            db = self.connect()
        try:
            row = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            return dict(row) if row else None
        finally:
            if owned:
                db.close()

    def get_campaign(self, campaign_id):
        with self.connect() as db:
            row = self.get_campaign_row(campaign_id, db)
            if row is None:
                return None
            orders = self._load_orders(db, campaign_id)
        return self._campaign_payload(row, orders)

    def list_campaigns(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            with self.connect() as db:
                orders = self._load_orders(db, row["id"])
            payload = self._campaign_payload(dict(row), orders)
            result.append({key: payload[key] for key in ("id", "name", "quota_cents", "counts", "usage")})
        return result

    # ---- orders ----------------------------------------------------
    def _load_orders(self, db, campaign_id):
        rows = db.execute(
            "SELECT * FROM campaign_orders WHERE campaign_id=? ORDER BY received_us, seq",
            (campaign_id,),
        ).fetchall()
        return [
            Order(
                order_id=row["id"],
                seq=row["seq"],
                received_us=row["received_us"],
                received_at=row["received_at"],
                coupon_cents=row["coupon_cents"],
                line_qty=row["line_qty"],
                sell_price_cents=row["sell_price_cents"],
                unit_cost_cents=row["unit_cost_cents"],
                supplier_fund_cents=row["supplier_fund_cents"],
                state=row["state"],
            )
            for row in rows
        ]

    def _campaign_payload(self, row, orders):
        view = evaluate(row["quota_cents"], orders)
        return {
            "id": row["id"],
            "name": row["name"],
            "quota_cents": row["quota_cents"],
            "created_at": row["created_at"],
            "orders": view["orders"],
            "counts": view["counts"],
            "usage": view["usage"],
        }

    def _validate_order(self, data):
        payload = {}
        for field in FIELDS:
            payload[field] = parse_int(data.get(field), "INVALID_" + field.upper())
        if payload["line_qty"] <= 0:
            raise DomainIssue("INVALID_LINE_QTY")
        for field in ("sell_price_cents", "unit_cost_cents", "supplier_fund_cents", "coupon_cents"):
            if payload[field] < 0:
                raise DomainIssue("INVALID_" + field.upper())
        if payload["supplier_fund_cents"] > payload["unit_cost_cents"] * payload["line_qty"]:
            raise DomainIssue("FUND_OVER_COST")
        if payload["coupon_cents"] > payload["sell_price_cents"] * payload["line_qty"]:
            raise DomainIssue("COUPON_OVER_REVENUE")
        return payload

    def submit_order(self, campaign_id, data):
        payload = self._validate_order(data)
        order_id = str(data.get("order_id") or "").strip() or uuid.uuid4().hex[:10]
        has_time = data.get("received_at") not in (None, "")
        received_at, received_us = parse_received(data.get("received_at"))
        with self.transaction() as db:
            campaign = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if campaign is None:
                raise DomainIssue("CAMPAIGN_NOT_FOUND", 404)
            existing = db.execute(
                "SELECT * FROM campaign_orders WHERE campaign_id=? AND id=?", (campaign_id, order_id)
            ).fetchone()
            if existing is not None:
                # 幂等重复提交：字段一致，且（若显式给了接单时间）时间也一致。
                same = all(existing[field] == payload[field] for field in FIELDS)
                same = same and (not has_time or existing["received_us"] == received_us)
                if not same:
                    raise DomainIssue("ORDER_CONFLICT", 409)
                return self._campaign_payload(dict(campaign), self._load_orders(db, campaign_id)), order_id
            seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS n FROM campaign_orders WHERE campaign_id=?", (campaign_id,)
            ).fetchone()["n"]
            stamp = _now()
            db.execute(
                "INSERT INTO campaign_orders(campaign_id,id,seq,received_at,received_us,line_qty,"
                "sell_price_cents,unit_cost_cents,supplier_fund_cents,coupon_cents,state,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (campaign_id, order_id, seq, received_at, received_us, payload["line_qty"],
                 payload["sell_price_cents"], payload["unit_cost_cents"], payload["supplier_fund_cents"],
                 payload["coupon_cents"], DRAFT, stamp, stamp),
            )
            orders = self._load_orders(db, campaign_id)
        return self._campaign_payload(dict(campaign), orders), order_id

    def _shift_state(self, campaign_id, order_id, action):
        """在事务内重算分配并执行签发/取消。重试幂等，不重复释放额度。"""
        with self.transaction() as db:
            campaign = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if campaign is None:
                raise DomainIssue("CAMPAIGN_NOT_FOUND", 404)
            orders = self._load_orders(db, campaign_id)
            view = evaluate(campaign["quota_cents"], orders)
            target = view["by_id"].get(order_id)
            if target is None:
                raise DomainIssue("ORDER_NOT_FOUND", 404)

            if action == "issue":
                if target["state"] == ISSUED:
                    # 重复签发：保持原状，不产生新承诺。
                    pass
                elif target["status"] == CANCELLED:
                    raise DomainIssue("ORDER_CANCELLED", 409)
                elif target["reason"] == "COUPON_CAUSES_LOSS":
                    raise DomainIssue("ORDER_LOSS", 409)
                elif not target["quota_granted"]:
                    raise DomainIssue("QUOTA_UNAVAILABLE", 409)
                else:
                    db.execute(
                        "UPDATE campaign_orders SET state=?, updated_at=? WHERE campaign_id=? AND id=?",
                        (ISSUED, _now(), campaign_id, order_id),
                    )
            elif action == "cancel":
                if target["state"] == CANCELLED:
                    pass  # 幂等：已取消不再重复释放
                else:
                    db.execute(
                        "UPDATE campaign_orders SET state=?, updated_at=? WHERE campaign_id=? AND id=?",
                        (CANCELLED, _now(), campaign_id, order_id),
                    )
            else:
                raise DomainIssue("BAD_REQUEST")

            orders = self._load_orders(db, campaign_id)
        return self._campaign_payload(dict(campaign), orders), order_id

    def issue_order(self, campaign_id, order_id):
        return self._shift_state(campaign_id, order_id, "issue")

    def cancel_order(self, campaign_id, order_id):
        return self._shift_state(campaign_id, order_id, "cancel")

    def ship_status(self, campaign_id, order_id):
        campaign = self.get_campaign_row(campaign_id)
        if campaign is None:
            raise DomainIssue("CAMPAIGN_NOT_FOUND", 404)
        with self.connect() as db:
            orders = self._load_orders(db, campaign_id)
        view = evaluate(campaign["quota_cents"], orders)
        target = view["by_id"].get(order_id)
        if target is None:
            raise DomainIssue("ORDER_NOT_FOUND", 404)
        return {
            "campaign_id": campaign_id,
            "order_id": order_id,
            "can_ship": target["can_ship"],
            "can_issue": target["can_issue"],
            "status": target["status"],
            "reason": target["reason"],
            "waitlist_position": target["waitlist_position"],
            "quota_granted": target["quota_granted"],
            "coupon_cents": target["coupon_cents"],
            "margin_with_coupon": target["margin_with_coupon"],
            "preempted": target["preempted"],
        }

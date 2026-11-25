from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.prepare import prepare_rows
from app.intake.service import load

CLEAN = [{'sku': 'A',
  'line_qty': '10',
  'list_price_cents': '1000',
  'sell_price_cents': '900',
  'supplier_fund_cents': '1000',
  'coupon_cents': '500',
  'unit_cost_cents': '600'},
 {'sku': 'B',
  'line_qty': '5',
  'list_price_cents': '2000',
  'sell_price_cents': '1800',
  'supplier_fund_cents': '0',
  'coupon_cents': '1000',
  'unit_cost_cents': '1200'},
 {'sku': 'C',
  'line_qty': '3',
  'list_price_cents': '500',
  'sell_price_cents': '500',
  'supplier_fund_cents': '300',
  'coupon_cents': '0',
  'unit_cost_cents': '400'}]


def row(**changes):
    item = dict(CLEAN[0])
    item.update(changes)
    return item


def calc(rows):
    items, issues = prepare_rows(rows)
    return calculate_rows(items), issues


def run(rows):
    items, issues = prepare_rows(rows)
    return decide_rows(calculate_rows(items)), issues


def run_profile(profile):
    return run(load(profile)["rows"])

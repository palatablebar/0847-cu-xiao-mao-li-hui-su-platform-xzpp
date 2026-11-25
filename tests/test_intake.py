import csv
import io

from app.catalog import SPEC
from app.errors import DomainIssue
from app.intake.service import load
from tests.domain_cases import CLEAN, row

EXPECTED = {'calc_case': {'coupon_cents': '0',
               'line_qty': '1',
               'list_price_cents': '1000',
               'sell_price_cents': '1000',
               'sku': 'Z',
               'supplier_fund_cents': '0',
               'unit_cost_cents': '600'},
 'calc_case_expected': '400',
 'calc_case_field': 'margin',
 'computed': 3,
 'first_label': 'A',
 'metric_field': 'margin',
 'metric_total': '6100',
 'prepared': 3,
 'value_approx': '3500',
 'value_field': 'margin'}


def make_file(tmp_path, rows, repeated=False, extra=False, name="sample.csv"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(SPEC["columns"])
    for index, item in enumerate(rows):
        values = [item.get(column, "") for column in SPEC["columns"]]
        if extra:
            values.append("surplus")
        writer.writerow(values)
        if repeated and index == 0:
            writer.writerow(SPEC["columns"])
    path = tmp_path / name
    path.write_text(stream.getvalue(), encoding="utf-8")
    return path


def test_clean_sample_is_accepted():
    data = load("clean")
    assert data["counts"]["accepted"] == EXPECTED["prepared"]
    assert data["counts"]["isolated"] == 0


def test_bom_is_removed_from_first_header():
    assert (SPEC_SAMPLE_BYTES := (load("dirty")["path"].read_bytes())).startswith(b"\xef\xbb\xbf")


def test_quoted_newline_is_one_logical_record(tmp_path):
    item = row()
    item[SPEC["columns"][1]] = "A\nB"
    data = load("clean", str(make_file(tmp_path, [item], name="quoted.csv")))
    assert data["counts"]["accepted"] == 1


def test_repeated_header_is_ignored(tmp_path):
    data = load("clean", str(make_file(tmp_path, [row(), row(**{SPEC["key"]: "SECOND"})], repeated=True, name="repeat.csv")))
    assert data["counts"]["ignored"] == 1
    assert any(issue["code"] == "REPEATED_HEADER" for issue in data["issues"])


def test_extra_column_is_isolated(tmp_path):
    data = load("clean", str(make_file(tmp_path, [row()], extra=True, name="extra.csv")))
    assert data["counts"]["accepted"] == 0
    assert any(issue["code"] == "COLUMN_COUNT" for issue in data["issues"])


def test_conflicting_duplicate_is_isolated(tmp_path):
    first = row()
    second = row()
    field = next(field for field, kind in SPEC["types"].items() if kind not in {"date", "date_optional", "datetime"})
    second[field] = "999999"
    data = load("clean", str(make_file(tmp_path, [first, second], name="conflict.csv")))
    assert data["counts"]["accepted"] == 0
    assert any(issue["code"] == "CONFLICT_DUPLICATE" for issue in data["issues"])

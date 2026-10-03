"""Contract loading and validation."""

import copy
from pathlib import Path

import pytest
import yaml

from data_contracts_platform.contract import ContractError, load, loads, parse

ROOT = Path(__file__).resolve().parents[2]
ORDERS = ROOT / "contracts" / "orders.yaml"
BASE = yaml.safe_load(ORDERS.read_text(encoding="utf-8"))


def test_published_contract_is_valid():
    c = load(ORDERS)
    assert (c.id, c.version, c.owner) == ("orders", "1.0.0", "checkout-team")
    assert list(c.datasets) == ["orders", "order_items"]
    assert c.datasets["orders"].fields["status"].allowed_values == (
        "placed",
        "paid",
        "shipped",
        "cancelled",
    )
    assert [f.name for f in c.datasets["order_items"].fields.values() if f.primary_key] == [
        "order_id",
        "line_no",
    ]
    assert c.freshness_seconds == 3600


def _broken(**changes):
    """A copy of the base contract with top-level keys replaced."""
    doc = copy.deepcopy(BASE)
    doc.update(changes)
    return doc


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        (_broken(apiVersion="v2.2.2"), "apiVersion"),
        (_broken(kind="Table"), "kind"),
        (_broken(id=""), "id must"),
        (_broken(version="1.0"), "version"),
        (
            _broken(team=[{"username": "a", "role": "consumer"}]),
            "exactly one member with role: owner",
        ),
        (
            _broken(team=[{"username": "a", "role": "owner"}, {"username": "b", "role": "owner"}]),
            "exactly one",
        ),
        (_broken(schema=[]), "schema must"),
        (_broken(schema=[{"name": "bad name", "properties": []}]), "identifier"),
        (
            _broken(schema=[{"name": "t", "properties": [{"name": "a", "logicalType": "uuid"}]}]),
            "logicalType",
        ),
        (
            _broken(
                schema=[
                    {
                        "name": "t",
                        "properties": [{"name": "a", "logicalType": "string", "required": "yes"}],
                    }
                ]
            ),
            "required must",
        ),
        (
            _broken(
                schema=[
                    {
                        "name": "t",
                        "properties": [{"name": "a", "logicalType": "string", "allowedValues": []}],
                    }
                ]
            ),
            "allowedValues",
        ),
        (
            _broken(
                schema=[
                    {
                        "name": "t",
                        "properties": [
                            {"name": "a", "logicalType": "string", "allowedValues": ["x", "x"]}
                        ],
                    }
                ]
            ),
            "distinct",
        ),
        (
            _broken(
                schema=[
                    {
                        "name": "t",
                        "properties": [
                            {"name": "a", "logicalType": "string"},
                            {"name": "a", "logicalType": "string"},
                        ],
                    }
                ]
            ),
            "defined twice",
        ),
        (
            _broken(
                schema=[{"name": "t", "properties": [{"name": "a", "logicalType": "string"}]}] * 2
            ),
            "defined twice",
        ),
        (_broken(slaProperties=[{"property": "freshness", "value": 0, "unit": "h"}]), "freshness"),
        (
            _broken(slaProperties=[{"property": "freshness", "value": 1, "unit": "week"}]),
            "freshness",
        ),
    ],
)
def test_invalid_contracts_are_rejected(doc, message):
    with pytest.raises(ContractError, match=message):
        parse(doc)


def test_all_problems_are_reported_at_once():
    with pytest.raises(ContractError) as err:
        parse(_broken(kind="Table", version="x", schema=[]))
    assert str(err.value).count("\n  - ") == 3


def test_yaml_tags_cannot_run_code():
    with pytest.raises(ContractError, match="not valid YAML"):
        loads("!!python/object/apply:os.system ['echo pwned']")


def test_non_mapping_is_rejected():
    with pytest.raises(ContractError, match="mapping"):
        loads("- just\n- a list\n")

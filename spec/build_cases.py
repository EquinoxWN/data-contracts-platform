"""Build spec/cases.json: contract changes with hand-written expected classifications.

Both the Python and the JavaScript classifiers must produce exactly these results. Expectations
are written by hand here, never computed by either implementation.

Usage:
    python spec/build_cases.py           # rewrite spec/cases.json
    python spec/build_cases.py --check   # fail if the committed file is stale
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BASE = yaml.safe_load((HERE.parent / "contracts" / "orders.yaml").read_text(encoding="utf-8"))
OUT = HERE / "cases.json"

Mutation = Callable[[dict], None]


def prop(doc: dict, dataset: str, field: str) -> dict:
    """The property dict for dataset.field."""
    ds = next(d for d in doc["schema"] if d["name"] == dataset)
    return next(p for p in ds["properties"] if p["name"] == field)


def drop_field(doc: dict, dataset: str, field: str) -> None:
    """Remove dataset.field."""
    ds = next(d for d in doc["schema"] if d["name"] == dataset)
    ds["properties"] = [p for p in ds["properties"] if p["name"] != field]


def set_sla(doc: dict, value: int | None, unit: str = "h") -> None:
    """Replace or remove the freshness SLA."""
    doc["slaProperties"] = (
        [] if value is None else [{"property": "freshness", "value": value, "unit": unit}]
    )


S, B = False, True  # safe, breaking

CASES: list[tuple[str, Mutation, list[list]]] = [
    ("no change", lambda d: None, []),
    (
        "field removed",
        lambda d: drop_field(d, "orders", "coupon_code"),
        [["field-removed", "orders.coupon_code", B]],
    ),
    (
        "optional field added",
        lambda d: d["schema"][0]["properties"].append({"name": "channel", "logicalType": "string"}),
        [["field-added", "orders.channel", S]],
    ),
    (
        "required field added",
        lambda d: d["schema"][0]["properties"].append(
            {"name": "currency", "logicalType": "string", "required": True}
        ),
        [["field-added", "orders.currency", S]],
    ),
    (
        "integer widened to number",
        lambda d: prop(d, "orders", "amount_cents").update(logicalType="number"),
        [["type-widened", "orders.amount_cents", S]],
    ),
    (
        "type changed integer to string",
        lambda d: prop(d, "orders", "amount_cents").update(logicalType="string"),
        [["type-changed", "orders.amount_cents", B]],
    ),
    (
        "timestamp changed to date",
        lambda d: prop(d, "orders", "placed_at").update(logicalType="date"),
        [["type-changed", "orders.placed_at", B]],
    ),
    (
        "required field became optional",
        lambda d: prop(d, "orders", "customer_id").update(required=False),
        [["became-optional", "orders.customer_id", B]],
    ),
    (
        "optional field became required",
        lambda d: prop(d, "orders", "coupon_code").update(required=True),
        [["became-required", "orders.coupon_code", S]],
    ),
    (
        "allowed value added",
        lambda d: prop(d, "orders", "status")["allowedValues"].append("refunded"),
        [["allowed-values-extended", "orders.status", B]],
    ),
    (
        "allowed value removed",
        lambda d: prop(d, "orders", "status")["allowedValues"].remove("cancelled"),
        [["allowed-values-narrowed", "orders.status", S]],
    ),
    (
        "allowed values constraint dropped",
        lambda d: prop(d, "orders", "status").pop("allowedValues"),
        [["allowed-values-removed", "orders.status", B]],
    ),
    (
        "allowed values constraint introduced",
        lambda d: prop(d, "order_items", "sku").update(allowedValues=["A-1", "B-2"]),
        [["allowed-values-added", "order_items.sku", S]],
    ),
    (
        "primary key changed",
        lambda d: prop(d, "order_items", "line_no").update(primaryKey=False),
        [["primary-key-changed", "order_items", B]],
    ),
    ("freshness loosened", lambda d: set_sla(d, 6), [["freshness-loosened", "orders", B]]),
    (
        "freshness tightened",
        lambda d: set_sla(d, 15, "min"),
        [["freshness-tightened", "orders", S]],
    ),
    ("freshness same in other unit", lambda d: set_sla(d, 60, "min"), []),
    ("freshness removed", lambda d: set_sla(d, None), [["freshness-removed", "orders", B]]),
    ("dataset removed", lambda d: d["schema"].pop(1), [["dataset-removed", "order_items", B]]),
    (
        "dataset added",
        lambda d: d["schema"].append(
            {
                "name": "refunds",
                "properties": [{"name": "refund_id", "logicalType": "string", "required": True}],
            }
        ),
        [["dataset-added", "refunds", S]],
    ),
    (
        "owner changed",
        lambda d: d["team"][0].update(username="payments-team"),
        [["owner-changed", "orders", S]],
    ),
    (
        "descriptions edited",
        lambda d: (
            d.update(description="Edited."),
            prop(d, "orders", "status").update(description="Edited."),
        ),
        [["description-changed", "orders", S], ["description-changed", "orders.status", S]],
    ),
    (
        "several changes at once",
        lambda d: (
            drop_field(d, "orders", "coupon_code"),
            prop(d, "orders", "status")["allowedValues"].append("refunded"),
            d["schema"][0]["properties"].append({"name": "channel", "logicalType": "string"}),
        ),
        [
            ["allowed-values-extended", "orders.status", B],
            ["field-removed", "orders.coupon_code", B],
            ["field-added", "orders.channel", S],
        ],
    ),
]


# Cases whose published (old) version differs from contracts/orders.yaml.
OLD_SIDE: list[tuple[str, Mutation, Mutation, list[list]]] = [
    (
        "number narrowed to integer",
        lambda d: prop(d, "orders", "amount_cents").update(logicalType="number"),
        lambda d: None,
        [["type-changed", "orders.amount_cents", B]],
    ),
    (
        "contract with no SLA gains one",
        lambda d: set_sla(d, None),
        lambda d: None,
        [["freshness-added", "orders", S]],
    ),
]


def build() -> str:
    """The cases file as JSON text."""
    cases = []
    rows = [(n, lambda d: None, m, e) for n, m, e in CASES] + OLD_SIDE
    for name, mutate_old, mutate_new, expect in rows:
        old, new = copy.deepcopy(BASE), copy.deepcopy(BASE)
        mutate_old(old)
        mutate_new(new)
        cases.append({"name": name, "old": old, "new": new, "expect": expect})
    return json.dumps({"cases": cases}, indent=1) + "\n"


def main() -> int:
    """Write the cases, or with --check compare them to the committed file."""
    text = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("stale: spec/cases.json (run python spec/build_cases.py)")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(CASES) + len(OLD_SIDE)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())

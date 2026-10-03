"""Change classification against the shared, hand-labelled cases in spec/cases.json."""

import json
from pathlib import Path

import pytest

from data_contracts_platform.contract import ContractError, parse
from data_contracts_platform.diff import diff, is_breaking

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "spec" / "cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_case(case):
    changes = diff(parse(case["old"]), parse(case["new"]))
    assert [[c.kind, c.path, c.breaking] for c in changes] == case["expect"]


def test_cases_cover_safe_and_breaking_changes():
    labels = [e[2] for c in CASES for e in c["expect"]]
    assert labels.count(True) >= 10
    assert labels.count(False) >= 10


def test_is_breaking():
    case = next(c for c in CASES if c["name"] == "field removed")
    assert is_breaking(diff(parse(case["old"]), parse(case["new"])))
    assert not is_breaking([])


def test_different_contracts_cannot_be_compared():
    other = dict(CASES[0]["new"], id="payments")
    with pytest.raises(ContractError, match="different contracts"):
        diff(parse(CASES[0]["old"]), parse(other))

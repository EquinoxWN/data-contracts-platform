"""Load and validate data contracts written in a subset of the Open Data Contract Standard v3."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TYPES = ("string", "integer", "number", "boolean", "date", "timestamp")
UNIT_SECONDS = {"m": 60, "min": 60, "h": 3600, "d": 86400}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
MAX_BYTES = 1_000_000


class ContractError(ValueError):
    """The document is not a valid data contract."""


@dataclass(frozen=True)
class Field:
    """One column of a dataset."""

    name: str
    logical_type: str
    required: bool
    primary_key: bool
    description: str
    allowed_values: tuple[Any, ...] | None


@dataclass(frozen=True)
class Dataset:
    """One table described by the contract."""

    name: str
    fields: dict[str, Field]


@dataclass(frozen=True)
class Contract:
    """A validated contract."""

    id: str
    name: str
    version: str
    owner: str
    description: str
    datasets: dict[str, Dataset]
    freshness_seconds: int | None


def load(path: str | Path) -> Contract:
    """Read and validate a contract file."""
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ContractError(f"{p}: larger than {MAX_BYTES} bytes")
    return loads(p.read_text(encoding="utf-8"), source=str(p))


def loads(text: str, source: str = "contract") -> Contract:
    """Parse YAML text (safe loader only) and validate it."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise ContractError(f"{source}: not valid YAML: {err}") from err
    return parse(doc, source)


def parse(doc: Any, source: str = "contract") -> Contract:
    """Validate a decoded document; every problem is reported at once."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        raise ContractError(f"{source}: a contract must be a mapping")
    if not str(doc.get("apiVersion", "")).startswith("v3."):
        errors.append("apiVersion must be v3.x")
    if doc.get("kind") != "DataContract":
        errors.append("kind must be DataContract")
    errors.extend(
        f"{key} must be a non-empty string"
        for key in ("id", "name")
        if not isinstance(doc.get(key), str) or not doc[key].strip()
    )
    if not isinstance(doc.get("version"), str) or not SEMVER.match(doc["version"]):
        errors.append("version must look like 1.2.3")
    owner = _owner(doc.get("team"), errors)
    datasets = _datasets(doc.get("schema"), errors)
    freshness = _freshness(doc.get("slaProperties", []), errors)
    if errors:
        raise ContractError(f"{source}:\n  - " + "\n  - ".join(errors))
    return Contract(
        id=doc["id"],
        name=doc["name"],
        version=doc["version"],
        owner=owner,
        description=str(doc.get("description", "")),
        datasets=datasets,
        freshness_seconds=freshness,
    )


def _owner(team: Any, errors: list[str]) -> str:
    """The username of the single team member with role owner."""
    owners = [
        m.get("username") for m in team or [] if isinstance(m, dict) and m.get("role") == "owner"
    ]
    if not isinstance(team, list) or len(owners) != 1 or not isinstance(owners[0], str):
        errors.append("team must list exactly one member with role: owner")
        return ""
    return owners[0]


def _datasets(schema: Any, errors: list[str]) -> dict[str, Dataset]:
    """Validate the schema list."""
    if not isinstance(schema, list) or not schema:
        errors.append("schema must be a non-empty list of datasets")
        return {}
    out: dict[str, Dataset] = {}
    for i, ds in enumerate(schema):
        name = ds.get("name") if isinstance(ds, dict) else None
        where = f"schema[{i}]"
        if not isinstance(name, str) or not NAME.match(name):
            errors.append(f"{where}.name must be an identifier")
            continue
        if name in out:
            errors.append(f"dataset {name} is defined twice")
            continue
        out[name] = Dataset(name, _fields(name, ds.get("properties"), errors))
    return out


def _fields(dataset: str, props: Any, errors: list[str]) -> dict[str, Field]:
    """Validate one dataset's properties."""
    if not isinstance(props, list) or not props:
        errors.append(f"{dataset}.properties must be a non-empty list")
        return {}
    out: dict[str, Field] = {}
    for i, p in enumerate(props):
        if (
            not isinstance(p, dict)
            or not isinstance(p.get("name"), str)
            or not NAME.match(p["name"])
        ):
            errors.append(f"{dataset}.properties[{i}].name must be an identifier")
            continue
        path = f"{dataset}.{p['name']}"
        if p["name"] in out:
            errors.append(f"{path} is defined twice")
            continue
        if p.get("logicalType") not in TYPES:
            errors.append(f"{path}.logicalType must be one of {', '.join(TYPES)}")
        errors.extend(
            f"{path}.{flag} must be true or false"
            for flag in ("required", "primaryKey")
            if not isinstance(p.get(flag, False), bool)
        )
        allowed = p.get("allowedValues")
        if allowed is not None and (
            not isinstance(allowed, list)
            or not allowed
            or len({repr(v) for v in allowed}) != len(allowed)
            or not all(isinstance(v, str | int | float | bool) for v in allowed)
        ):
            errors.append(f"{path}.allowedValues must be a non-empty list of distinct scalars")
            allowed = None
        out[p["name"]] = Field(
            name=p["name"],
            logical_type=str(p.get("logicalType")),
            required=p.get("required", False) is True,
            primary_key=p.get("primaryKey", False) is True,
            description=str(p.get("description", "")),
            allowed_values=tuple(allowed) if allowed is not None else None,
        )
    return out


def _freshness(sla: Any, errors: list[str]) -> int | None:
    """The freshness SLA in seconds, if the contract has one."""
    if not isinstance(sla, list):
        errors.append("slaProperties must be a list")
        return None
    entries = [s for s in sla if isinstance(s, dict) and s.get("property") == "freshness"]
    if not entries:
        return None
    if len(entries) > 1:
        errors.append("slaProperties has more than one freshness entry")
        return None
    value, unit = entries[0].get("value"), entries[0].get("unit")
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or unit not in UNIT_SECONDS
    ):
        errors.append(
            f"freshness needs a positive integer value and a unit in {sorted(UNIT_SECONDS)}"
        )
        return None
    return value * UNIT_SECONDS[unit]

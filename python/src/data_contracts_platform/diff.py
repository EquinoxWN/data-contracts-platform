"""Classify every difference between two versions of a contract as safe or breaking for consumers."""

from __future__ import annotations

from dataclasses import dataclass

from data_contracts_platform.contract import Contract, ContractError, Dataset, Field

# Type changes every consumer can still read.
WIDENING = {("integer", "number")}


@dataclass(frozen=True)
class Change:
    """One difference, seen from a downstream consumer."""

    kind: str
    path: str
    breaking: bool
    detail: str

    def __str__(self) -> str:
        label = "BREAKING" if self.breaking else "safe"
        return f"{label:<9} {self.path:<28} {self.kind}: {self.detail}"


def diff(old: Contract, new: Contract) -> list[Change]:
    """All changes from old to new, in a stable order."""
    if old.id != new.id:
        raise ContractError(f"different contracts: {old.id!r} vs {new.id!r}")
    out: list[Change] = []
    if old.owner != new.owner:
        out.append(Change("owner-changed", new.id, False, f"{old.owner} -> {new.owner}"))
    if old.description != new.description:
        out.append(Change("description-changed", new.id, False, "contract description edited"))
    out += _freshness(old, new)
    for name, ds in old.datasets.items():
        if name not in new.datasets:
            out.append(Change("dataset-removed", name, True, "consumers of this table lose it"))
        else:
            out += _dataset(ds, new.datasets[name])
    out += [
        Change("dataset-added", name, False, "new table")
        for name in new.datasets
        if name not in old.datasets
    ]
    return out


def is_breaking(changes: list[Change]) -> bool:
    """True if any change breaks a consumer."""
    return any(c.breaking for c in changes)


def _freshness(old: Contract, new: Contract) -> list[Change]:
    """Changes to the freshness SLA."""
    a, b = old.freshness_seconds, new.freshness_seconds
    if a == b:
        return []
    if a is None:
        return [Change("freshness-added", new.id, False, f"data at most {b}s old")]
    if b is None:
        return [Change("freshness-removed", new.id, True, "no freshness guarantee any more")]
    if b > a:
        return [Change("freshness-loosened", new.id, True, f"{a}s -> {b}s")]
    return [Change("freshness-tightened", new.id, False, f"{a}s -> {b}s")]


def _dataset(old: Dataset, new: Dataset) -> list[Change]:
    """Changes inside one table."""
    out: list[Change] = []
    old_pk = [f.name for f in old.fields.values() if f.primary_key]
    new_pk = [f.name for f in new.fields.values() if f.primary_key]
    if old_pk != new_pk:
        out.append(Change("primary-key-changed", new.name, True, f"{old_pk} -> {new_pk}"))
    for name, f in old.fields.items():
        path = f"{new.name}.{name}"
        if name not in new.fields:
            out.append(Change("field-removed", path, True, "consumers selecting it will fail"))
        else:
            out += _field(path, f, new.fields[name])
    for name, f in new.fields.items():
        if name not in old.fields:
            kind = "required" if f.required else "optional"
            out.append(
                Change("field-added", f"{new.name}.{name}", False, f"new {kind} {f.logical_type}")
            )
    return out


def _field(path: str, old: Field, new: Field) -> list[Change]:
    """Changes to one column."""
    out: list[Change] = []
    if old.logical_type != new.logical_type:
        widened = (old.logical_type, new.logical_type) in WIDENING
        kind = "type-widened" if widened else "type-changed"
        out.append(Change(kind, path, not widened, f"{old.logical_type} -> {new.logical_type}"))
    if old.required and not new.required:
        out.append(Change("became-optional", path, True, "consumers may now receive nulls"))
    elif new.required and not old.required:
        out.append(Change("became-required", path, False, "nulls no longer allowed"))
    a, b = old.allowed_values, new.allowed_values
    if a is not None and b is None:
        out.append(Change("allowed-values-removed", path, True, "any value may now appear"))
    elif a is None and b is not None:
        out.append(Change("allowed-values-added", path, False, f"restricted to {list(b)}"))
    elif a is not None and b is not None:
        added = [v for v in b if v not in a]
        dropped = [v for v in a if v not in b]
        if added:
            out.append(Change("allowed-values-extended", path, True, f"new values {added}"))
        if dropped:
            out.append(
                Change("allowed-values-narrowed", path, False, f"values no longer used {dropped}")
            )
    if old.description != new.description:
        out.append(Change("description-changed", path, False, "field description edited"))
    return out

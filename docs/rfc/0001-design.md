# RFC 0001: data-contracts-platform design

- **Status:** Accepted (M1 implemented)
- **Author:** EquinoxWN
- **Created:** 2026

## Problem

A producing team renames a column, adds an order status, or slows a pipeline from hourly to daily.
Nothing fails in their service, but a dozen dashboards and models downstream silently break or
show wrong numbers, and the consumers find out days later. The interface between producer and
consumer is implicit. A data contract makes it explicit and lets CI refuse a change that would
break the people relying on it, before it merges.

## Goals

- Producers describe each dataset in a YAML contract: schema (types, required, primary key,
  allowed values), field meanings, a freshness SLA and an owner.
- A CLI validates contracts and classifies every difference between two versions as safe or
  breaking for consumers, with a reason.
- On a pull request, CI compares the changed contracts with the versions published on the base
  branch and fails on any breaking change, writing a summary to the job page.
- The same classification runs in JavaScript for the catalog page, proven identical by shared,
  hand-labelled cases.
- Later: PR comments naming affected consumers (M2), batch quality checks with a quarantine table
  and owner alerts (M2-M3), a catalog page (M3).

## Non-goals

- Full Open Data Contract Standard compliance in M1 (see the format notes below).
- Enforcing contracts on data at runtime (M2).
- Running as a hosted production service.

## Proposed design

![architecture](../architecture.png)

```
contracts/*.yaml (pull request) ─┐
                                  ├─► datacontract check-pr --base origin/main ─► safe: pass
git show origin/main:contracts/… ─┘        (validate, then diff each contract)  └► breaking: fail + job summary
```

### Contract format

Field names follow the Open Data Contract Standard v3 where it defines them: `apiVersion`,
`kind`, `id`, `version`, `team` (one member with `role: owner`), `schema` with `properties`
(`logicalType`, `required`, `primaryKey`, `description`) and `slaProperties` (a `freshness`
entry with `value` and `unit`). Two simplifications are this project's own and are documented as
such: `allowedValues` on a property, and `timestamp` as a logical type. YAML is read with the safe
loader only, files over 1 MB are refused, and every validation problem is reported at once.

### Classification rules (consumer view, ADR 0002)

| Change | Verdict | Why |
|---|---|---|
| Field or dataset removed, contract removed | breaking | Queries that select it fail |
| Field or dataset added, contract added | safe | Existing queries are unaffected |
| `integer` to `number` | safe | Every integer is still a valid number |
| Any other type change (including `number` to `integer`, `timestamp` to `date`) | breaking | Parsing or precision changes |
| Required becomes optional | breaking | Consumers may now receive nulls |
| Optional becomes required | safe | Fewer nulls than promised |
| New allowed value | breaking | `CASE` statements and enums do not handle it |
| Allowed value dropped, or a constraint introduced | safe | Values consumers already handle |
| Allowed-values constraint dropped | breaking | Any value may now appear |
| Primary key changed | breaking | Joins and de-duplication change meaning |
| Freshness SLA loosened or removed | breaking | Data may be older than consumers rely on |
| Freshness tightened or added; owner or description edited | safe | No consumer is worse off |

A rename appears as a removal plus an addition, so it is breaking, which is correct for every
consumer that selects the old name.

### Pull request check

`check-pr` lists contracts in the working tree and at the base ref (`git ls-tree`), reads the
published version with `git show`, and diffs each one. Git is called with a fixed argument list
and no shell; the base ref must match a plain branch or commit pattern, so it can never be read
as a git option. CI passes `github.base_ref` through an environment variable, not by
interpolating it into the script.

## Alternatives considered

| Option | Why not (yet) |
|---|---|
| Schema-registry compatibility modes (Avro/Protobuf BACKWARD, FORWARD) | Covers types only; says nothing about allowed values, freshness or ownership, and needs a registry. |
| dbt model contracts | Enforced only inside dbt builds, after the change is made; consumers outside dbt are not protected. |
| Hand-written review checklist | Depends on reviewers remembering every rule; the rules here are executable and tested. |
| Treat new allowed values as safe | Common in tooling, but it is exactly the change that silently breaks `CASE` mappings and enum parsers downstream (ADR 0002). |
| Classify only in Python, render results in the catalog | The catalog would need a server; a JS classifier lets it work as a static page, and shared cases keep the two identical. |

## Measurement plan

- M1: 25 hand-labelled change cases classified identically by Python and JavaScript; the CLI's
  exit codes and the PR check tested against a real temporary git repository.
- M2: PR comment with affected consumers; quarantine counts on a demo pipeline.
- M3: a screenshot of CI blocking a breaking change, and before/after data-incident counts in the
  demo scenario.

## Milestones

- **M1 (done):** contract format and validation, classification rules, `datacontract` CLI
  (`validate`, `diff`, `check-pr`), JS classifier, CI gate on pull requests.
- **M2:** consumer registry and PR comments; Soda Core quality checks with a quarantine table.
- **M3:** owner alerts and metrics, catalog page, the before/after demo.

## Risks and open questions

- Some teams consider a new enum value safe. The rule is deliberately strict; an explicit
  override with a reason is an M2 option, so exceptions stay visible.
- Moving to full ODCS needs JSON-schema validation and a migration for `allowedValues`.
- The PR check needs the base branch fetched (`fetch-depth: 0`); a shallow clone makes the base
  ref unknown and the check fails closed with exit code 2.

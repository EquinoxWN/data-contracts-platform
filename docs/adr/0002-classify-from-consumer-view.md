# ADR 0002: Classify changes from the consumer's point of view, strictly

- **Status:** Accepted

## Context

Whether a change is "breaking" depends on who is asked. For a producer, adding a new order status
is a feature. For an analyst whose dashboard maps each status to a colour, or a service that parses
the status into an enum, the same change produces blanks, errors or wrong totals. Schema-registry
compatibility modes only look at types, and most contract tools treat a new enum value as safe.

## Decision

Every rule is written from the consumer's side: a change is breaking if any reasonable consumer
written against the old contract can fail or produce a wrong answer without changing its code.
That makes new allowed values, a dropped allowed-values constraint, a looser freshness SLA,
required-to-optional and every type change except `integer` to `number` breaking. When in doubt,
the rule is strict; CI blocking a harmless change costs a review, while a missed break costs a
data incident.

## Consequences

- Producers sometimes need a major-version contract or a coordinated rollout for changes they see
  as small. That friction is the point: it starts the conversation before the incident.
- The rules are a table in the RFC and 25 hand-labelled cases in `spec/cases.json`, so a
  disagreement becomes a reviewed pull request against the cases rather than a silent default.
- An explicit, logged override for a specific change is left for M2, so exceptions stay visible
  instead of loosening the rules for everyone.

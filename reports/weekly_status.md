# Weekly status, week ending 2026-11-20

**Overall: AMBER**

| Area | Status | Why |
|---|---|---|
| Schedule | green | committed finish 2027-01-19 is on or before the target 2027-02-26 |
| Quality | green | 25 of 25 legacy statements validated by parity, 0 open divergences |
| Risk | amber | 1 high finding without an agreed decision |

## Forecast

- Scope: 7 work packages, 108.5 points from the code analysis
- Finish, 50% likely: 2026-12-11; committed (85% likely, from past engagements): 2027-01-19; target: 2027-02-26

## Decisions needed

- F03 (high): Passwords are stored in plain text. Proposed: Out of scope for a like-for-like migration: raise with the customer's security lead and agree a hashing change as a separate, tested step
- F07 (low): Child tables have no foreign keys. Proposed: Count orphans in the customer's production copy before migration; agree whether to drop or quarantine them

## Decided this week

- F01: Order, status and line items become one document, written atomically; the stock decrement and the order insert run in one multi-document transaction on the Atlas replica set (Customer architect + Delivery tech lead, 2026-11-18)
- F02: Order ids move to an atomic findOneAndUpdate($inc) on the sequences collection; id format unchanged (Delivery tech lead, 2026-11-18)
- F04: Keep legacy inner-join behaviour (accounts without a banner, orders without a status are not returned); parity tests pin it (Customer product owner, 2026-11-19)
- F05: Keep % and _ as wildcards in search for this release; product owner to decide on escaping afterwards (Customer product owner, 2026-11-19)
- F06: Money as Decimal128; totals reconciled after each migration rehearsal (Delivery tech lead, 2026-11-17)

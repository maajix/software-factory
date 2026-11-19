# Factory tickets

A new project uses one folder per effort. Small changes need one ticket. Add a feature contract
when several tickets share requirements or when a consequential design decision needs a durable home.

```text
docs/work/
  overdue-reminders/
    contract.md
    01-queue-reminder.md
    02-show-reminder-in-activity.md
```

An existing factory profile can keep its tracker root and nested `issues/` folders.

```markdown
# 01 - Queue an overdue invoice reminder

Type: implementation
Status: needs-plan-review
Plan-Approval: pending
Blocked by: -
Contract: <revision if the effort has a contract>

## Outcome

An eligible overdue invoice queues one reminder when the daily billing job runs.

## Acceptance

- The job queues a reminder for an eligible invoice. A retry leaves the outbox with one entry.
- Paid, void, and opted-out invoices leave the outbox unchanged.

## Proof

Run the registered job in the billing integration test and assert on the persisted outbox.
The eligible case fails against the current code.
```

The filename supplies the stable number. Use `Type: task` for maintenance work the factory should
run. List prerequisite ticket numbers under `Blocked by:`. Use `Priority: high` or `Priority: low`
when order matters among runnable tickets. The default is normal. Add a producer and a consumer to
the proof when behavior crosses an interface. Keep optional context as links to existing files.

Use `Status: draft` while shaping a plan. Use `needs-plan-review` once it is ready and open it with
`factory plan-review <effort-or-issue>`. The CLI sets `Status: open` and records `Plan-Approval` after approval.
The receipt covers the plan content and shared contract revision. Status and ordinary comments can
change during delivery. Acceptance, dependencies, and other plan edits require a new approval.
Record requirement changes in the plan or the contract.
The board shows those issues in Plan review even when their status says `open`.

The contract records the shared outcome, boundaries, invariants and decisions. For an outcome that
depends on several tickets, include a scenario that exercises them together through the public entry
point. The factory uses it when verifying the implementation. Its hash is generated
by `factory contract <effort>`. After a contract edit, the queue holds the entire effort until every
unfinished build ticket carries the current revision. Active runs verify their original revision
again before moving forward after research, a build, or review. Use `/factory:feature revise <effort>`
for requirement changes, including changes already reflected in code. Reconcile all affected tickets
before restamping them. Record shipped behavior through a follow-up ticket.

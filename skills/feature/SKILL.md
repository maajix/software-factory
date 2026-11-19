---
name: feature
description: Turn a feature or fix into factory tickets and submit the finished plans for approval in Plannotator. Use revise to reconcile an existing effort, or review to reopen its plan approval.
argument-hint: "<idea> | revise <effort> <change> | review <effort-or-issue>"
---

# Factory feature

Read [the ticket format](../../docs/TICKETS.md) and the project's factory profile. Use the tracker
root and layout in that profile. Work from the user's idea, current code, and any related tickets or
design. In an indexed repo, start code navigation with CodeGraph. Reuse the project's vocabulary.
Use a short kebab-case effort directory and stable ticket numbers.
For an approved external design, link it in the contract and carry over only the decisions, open
questions, and proof needed for the tickets.

## Shape

1. Find the existing entry point and a test or scenario at which the change is observable. For a
   clear, localized change, write one ticket with its outcome and proof.
2. For a changed contract or persistent state, trace a representative request from its entry point
   through producers and consumers to the observable result. Check relevant edge cases, permissions,
   older data, rollout, and retries. Check where eligibility can change between selection and
   durable write, or again before a queued effect is delivered.
3. Find answers in code, docs, and previous decisions. Group remaining decisions that materially
   change acceptance or rollout in one short batch, with the consequence and a recommendation for
   each. Wait for those answers before publishing affected tickets as open.
4. Write a contract for shared requirements. Start with one ticket and add another only when it can
   deliver a separately verifiable outcome. Prefer a first ticket that proves the new path through
   every layer it crosses. For outcomes that depend on multiple tickets, record one shared scenario
   in the contract for `/factory:feature-review --implemented`. For irreversible changes, new persistent
   contracts, or several independent integrations, have one fresh reader check for missing decisions,
   broken consumers, and gaps in verification. Resolve specific findings before opening the tickets.
5. Write the tickets using the configured layout. Use `Status: needs-plan-review` and
   `Plan-Approval: pending` for finished plans. When there is a contract, stamp each ticket
   using `factory contract <effort>`. Submit the finished documents for approval below.

## Revise an existing effort

1. Read the current contract, every ticket in the effort, any delivered evidence, and changed code.
   Identify affected outcomes, tests, priorities, and dependency edges. Include indirect consumers.
   If the user wants a behavioral change and the code already reflects it, record it in the contract
   and update the remaining work to reflect the current behavior.
2. Update `contract.md` first. Reconcile every unfinished ticket with it. Preserve ticket numbers
   and record why a ticket was superseded. Open a follow-up for changed behavior that already
   shipped. Reopen an unmerged delivery that needs another build. A claimed run can finish its
   current phase and will park if its contract has changed.
3. Set each unfinished ticket's `Contract:` header using `factory contract <effort>`. Review its outcome,
   proof and dependencies. Set finished revised plans to `needs-plan-review` and clear their prior approval
   with `Plan-Approval: pending`. Leave a claimed ticket in its current run until the engine parks it.
4. Submit the finished documents for approval below. Report the affected ticket IDs and any pending decisions.

## Approve finished plans

Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory" plan-review <effort-or-issue>` as soon as the documents
are ready. This is also the action for `review <effort-or-issue>`. An effort opens its contract and every
pending finished issue together. A ticket reference opens that issue and its contract. Let the command
wait for the user in Plannotator. The CLI opens approved tickets for the queue.

- On `approved`, summarize approved tickets and any optional review notes. Confirm the frontier with `factory queue`.
- On `annotated`, reconcile the returned feedback with the contract and all affected tickets. Submit the
  revised plans for a new decision. Ask only for material unresolved product choices.
- On dismissal or a startup error, report that approval is pending. Resume with `/factory:feature review`.

Leave implementation to `/factory:run`. Keep a ticket's proof in the ticket and shared decisions in
the contract.

---
name: feature-review
description: Review a factory feature plan, or verify the integrated behavior after implementation with --implemented.
argument-hint: "<effort> [--implemented]"
---

# Factory feature review

For `--implemented`, use the implementation verification below. Otherwise, review the plan.

Locate the effort under the configured tracker root. Use one fresh, read-only agent. Pass it the
effort path, repo root, and the rubric below. Leave the shaping conversation out of its context.
A different model is helpful when one is available at similar cost. Sonnet is the default.

## Review rubric

Read the feature contract, tickets and relevant existing code. Trace the feature from the normal
entry point to an observable result. Check whether state can change before the write that
records the work, and again before a queued or retried effect executes.
For a migration or staged rollout, trace the same request during cutover and after rollback.
Check which version owns writes, which consumers can read new data, and which external effects
have already happened.

Report only a gap that affects behavior, risks incorrect state, or makes verification unreliable.
For each finding, cite a contract, ticket or symbol and give a concrete example. Say whether the
repo already resolves it, the owner must decide, or implementation must handle it. Flag any
acceptance criterion that promises more than its proof demonstrates. If the plan is sufficient,
return PASS. Leave named open decisions alone unless a ticket depends on treating one as settled.

## Resolve

Check each finding against the repo. Report only findings that hold up. If the user has authorized
revisions, apply confirmed changes through the feature reconciliation workflow. Bring unresolved
product decisions back together, with consequences. Leave findings and decisions in the relevant
ticket or contract so they survive the session.

Submit the resulting finished issue plans through the approval step in [Factory feature](../feature/SKILL.md).
Plannotator captures the owner's decision on the current Markdown revisions.

## Verify the implementation

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory" feature-evidence <effort>` from the project root.
   Review the current contract, ticket acceptance, checkout commits, and any missing deliveries.
   Use completed ticket checks as historical evidence. If a branch was squash-merged or the
   contract changed, establish the affected behavior on the current checkout. Record any unfinished
   work or unavailable checkout as a limit of the review. If a submodule's parent pointer and
   checkout differ, verify the parent-pinned version before attributing proof to the parent commit.
2. Map the contract guarantees to existing proofs. Run the smallest current test or scenario that
   exercises the feature through its normal entry point and observes the outcome across ticket
   boundaries. For asynchronous work, inspect the final consumer or side effect. Add one failure
   or compatibility case when a plausible failure could survive the ticket gates. Prefer local
   fixtures and existing checks. Reuse their evidence and results for all covered guarantees.
3. If a consequential gap remains, use one fresh read-only reviewer. Give it the current contract,
   exact checkout commits, the scoped code path, and the proof already available. Ask for a concrete
   failing scenario or the minimum check to resolve each gap. Use the review to target a test or
   inspection and distinguish confirmed failures from unresolved findings.
4. Run `feature-evidence` again. If the checked commits, contract or tickets changed, repeat affected checks.
   A dirty checkout can provide working-tree evidence. Attribute commit-level verification only
   to a clean checkout at the recorded commits. Mark the result passed only when all guarantees
   have proof and all required deliveries are accounted for.
5. Write a short `verification.md` alongside the tickets with the contract or ticket revisions,
   exact commits, checked guarantees, commands and results, and any failures or gaps. Reuse this
   report while its revisions, commits, and proof are current. Send confirmed regressions back
   through the owner ticket or a follow-up ticket. For a changed requirement, use `/factory:feature revise`.

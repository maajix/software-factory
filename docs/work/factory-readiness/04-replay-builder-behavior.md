# 04 - Score builder lessons with executable replays

Type: implementation
Status: resolved
Plan-Approval: a1633b142cf32c584d3962aba498845c416c599297ce9129dd30a977d787e854
Blocked by: 03
Contract: b82671dc9739ef0c

## Outcome

The Factory can qualify a builder instruction against runnable tasks with independent acceptance
checks.

## Acceptance

- Baseline and candidate builders work from identical starting code in separate disposable
  checkouts. Their patches are scored by the same prewritten tests.
- Evidence distinguishes a genuine improvement, a regression, and an inconclusive comparison.
  Adoption requires an improvement and preservation of the passing behavior.
- The learner's proposal, intended replay, and individual outcomes stay available for diagnosis.
  A builder's reported success alone cannot satisfy the gate.

## Proof

Run a real paired replay through the Factory CLI on a small executable fixture. Verify the before
and after acceptance results independently. Test the rejected candidate path and confirm that
neither coach run can change the comparison inputs.

## Comments


- factory, 2026-11-19: Plannotator requested changes.

  # File Feedback

  The following feedback is on the files under review, one section per file, in the order they were given for review.

  ## docs/work/factory-readiness/contract.md

  I've reviewed this document and have 1 piece of feedback:

  ### 1. (lines 3–8) Feedback on: "Codex"
  > factory is also used by claude code, fyi. Not only codex.

  ---

- factory, 2026-11-19: Plannotator requested changes.

  # File Feedback

  The following feedback is on the files under review, one section per file, in the order they were given for review.

  ## docs/work/factory-readiness/02-codex-ui-evidence.md

  I've reviewed this document and have 2 pieces of feedback:

  ### 1. (line 1) [🔍 Verify this] Feedback on: "Codex"
  > This seems like an assumption. Verify by reading the actual code before proceeding.

  ### 2. (lines 12–13) Feedback on: "Codex"
  > Make sure the factory and all tickets work for potentially any agent not specifically for codex only

  ### Label Summary

  - **🔍 Verify this**: 1

  ---

- factory, 2026-11-19: Built on branch `feature/minor-builder-replay` in .. Review it and merge, or set Status back to open with a comment saying what is wrong. PR text: `docs/work/factory-readiness/runs/20261119-162505424543-04-factory-readiness/pr.md`

  Factory run `20261119-162505424543-04-factory-readiness`.

- factory, 2026-11-19: Owner accepted the delivery based on the passed gates and independent review.

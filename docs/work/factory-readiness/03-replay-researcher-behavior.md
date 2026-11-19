# 03 - Replay researcher behavior before adopting a lesson

Type: implementation
Status: resolved
Plan-Approval: 9fcf1476243b7c561403a8bb2cc9fcc10b2d1739fb3e97f088ac802a761d6d9e
Blocked by: -
Contract: b82671dc9739ef0c

## Outcome

The Factory can test a proposed researcher instruction on independent planning cases before
making it active.

## Acceptance

- Committed cases can test whether the researcher proceeds when a requirement is settled and
  asks for a decision when a consequential requirement is unresolved.
- The Factory compares the current and proposed instructions in fresh contexts using the same
  cases. It adopts a change only when the candidate fixes a scored failure and preserves the
  passing cases.
- The existing reviewer replay works with its current records. An unqualified proposal remains
  available for manual evaluation.

## Proof

Run one paired replay through the CLI with fresh agents and examples outside the learner's
proposal evidence. Check the score against the committed assertions and verify adoption in a
disposable factory checkout.
Exercise the passing baseline and regression cases in the Factory unit gate.

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

- factory, 2026-11-19: Built on branch `feature/minor-researcher-replay` in .. Review it and merge, or set Status back to open with a comment saying what is wrong. PR text: `docs/work/factory-readiness/runs/20261119-115028838490-03-factory-readiness/pr.md`

  Factory run `20261119-115028838490-03-factory-readiness`.

- factory, 2026-11-19: Owner accepted the delivery based on the passed gates and independent review.

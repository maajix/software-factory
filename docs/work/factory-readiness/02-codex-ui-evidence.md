# 02 - Deliver UI tickets across agent runners

Type: implementation
Status: resolved
Plan-Approval: 69b9be582d665ee3419f86ad9f35980e7a084173e46e8089acc0ccd447b3a777
Blocked by: -
Contract: b82671dc9739ef0c
Evaluation: a3641ecc241062b7

## Outcome

Any builder that follows the Factory CLI protocol can receive the required UI design skill with
its build prompt. The Factory checks that handoff and the live UI review with the same rules
across agent runners.

## Acceptance

- The project can point to the installed `emil-design-eng` skill with an optional UI review
  setting. The Factory attaches the skill to builders when the brief anticipates UI or a prior
  build round has touched UI files.
- The UI handoff is tied to the current spawn and its prompt content. A missing or altered
  handoff cannot act as proof. The shared CLI proof works for agents that have no native skill
  tool or transcript hook. Existing Claude Code transcript evidence still works.
- An unanticipated UI change prompts an appropriately guided follow-up before delivery. A UI
  review records what it checked in the browser and what it observed. For a small change such as
  a label correction, that concise record is enough.
- When acceptance depends on layout, responsive behavior, or a comparable visual difference,
  keep the relevant screenshots in the effort archive. Delivery waits for evidence appropriate
  to the ticket's acceptance criteria.

## Proof

Reproduce the current CLI result being blocked when a UI change has no skill evidence. Drive a
build and review through `factory next` and `factory record`. Test valid, missing, and altered
handoffs and keep the existing native skill verification test. Exercise a small browser-verified
change without a screenshot and a visual change that requires one. A bare `PASS` leaves both
undelivered. For the visual case, check the relevant narrow and wide layouts in a real browser
and inspect the archived evidence.

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

- factory, 2026-11-19: Built on branch `feature/minor-ui-evidence` in .. Review it and merge, or set Status back to open with a comment saying what is wrong. PR text: `docs/work/factory-readiness/runs/20261119-115028747575-02-factory-readiness/pr.md`

  Factory run `20261119-115028747575-02-factory-readiness`.

- factory, 2026-11-19: Owner accepted the delivery based on the passed gates and independent review.

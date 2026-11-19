# 01 - Detect GitHub Actions run steps

Type: task
Status: resolved
Plan-Approval: e5b288d428fd64cedf708c8b68da5196e9ab5e8dd84d9aa6d84a39257a9d0a7e
Blocked by: -
Contract: b82671dc9739ef0c

## Outcome

Factory initialization surfaces the existing CI test command in the pickup pilot.

## Acceptance

- `factory detect` includes ordinary GitHub Actions `- run: command` steps in its CI hints.
- Existing CI hints from mapping-style `run:` and Bitbucket `script:` entries continue to work.
- Block markers and YAML step metadata stay out of the command hints.

## Proof

Reproduce detection on the Python pickup fixture and check the emitted command. Add a small
regression fixture for existing syntax and a block step. Run the Factory unit gate.

## Observation

The approved Codex pilot exposed an empty CI command list on a workflow with a single inline
GitHub Actions step. The test command had to be read from the workflow manually.

Evaluation: fb56703aeda487cd

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

- factory, 2026-11-19: Built on branch `bugfix/patch-detect-github-actions-steps` in .. Review it and merge, or set Status back to open with a comment saying what is wrong. PR text: `docs/work/factory-readiness/runs/20261119-115000634581-01-factory-readiness/pr.md`

  Factory run `20261119-115000634581-01-factory-readiness`.

- factory, 2026-11-19: Owner accepted the delivery based on the passed gates and independent review.

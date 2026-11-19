---
name: eval
description: Use when a factory user or agent notices a concrete factory bug, efficiency opportunity or missing feature. Replay the issue, open an improvement ticket when supported, or audit scoped test and code quality.
argument-hint: "[run <id> | report <observation> | ticket <id> | configure <checkout> | tests <path> | structure <path>]"
---

# Factory evaluation

Use `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory"` from the source project. Evaluate the result of
a run against its ticket, branch and gate evidence. Record the actual result, expected result and
how to replay the difference. For a speed claim, measure the same workload and model settings and
record repeats, elapsed time, token use and correctness. Do not include real customer data.

- With no argument, run `factory eval` and `factory status`. Show observations and recent run outcomes.
- When you notice a concrete factory issue during ordinary work, replay it using the smallest safe
  example. Save it with `factory eval report --summary ... --observed ... --expected ... --check ...`.
  Include `--baseline <result>` if the result is verified and the project has a feedback checkout.
  This writes a ticket awaiting plan approval. Submit it through `factory --root <checkout> plan-review`
  using its effort or issue reference. With no replay yet, return the saved observation ID.
- For `configure <checkout>`, use `factory eval configure <checkout>` to choose the initialized
  development checkout that receives verified factory feedback from this project.
- For `ticket <id>`, read the observation with `factory eval show <id>`. Independently verify the
  reported behavior on a clean reference checkout. Keep the baseline and precise pass condition.
  If the result justifies a change to the factory, create its plan using `factory eval ticket
  <id> --checkout <separate factory development checkout> --baseline <measured result>`. Use an
  existing initialized checkout if available. Submit the finished plan for Plannotator approval.
  Run the approved queue with the stable plugin loaded.
  Include the same replay after the change and judge it against the original baseline.

## Scoped test and structure audits

- For `tests <path>`, name the user-facing or integration behavior each candidate protects, and the
  exact regression that would make it fail. Find duplicated coverage, mock-only assertions, expected
  values derived from production logic, and assertions tied to private implementation. Keep distinct
  failure coverage across layers, compatibility checks, and negative guarantees that still apply.
  To propose removing a test, name what proves retained coverage and run that check.
- For `structure <path>`, trace what must change together and what changes independently. Use
  CodeGraph first where indexed. Identify one concrete change or failure that exposes duplicated
  policy, hidden dependencies, leaking internals, or unused indirection. Prefer a bounded refactor
  with a proof through the current interface.

Return findings with evidence and proposed tickets. This command evaluates and records work. The
build queue owns code edits, test deletions, and architecture changes.

For reusable workflow corrections that only require an instruction change, use `/factory:learn`.
Choose a ticket when the improvement needs changes to the factory engine, integration or tests.

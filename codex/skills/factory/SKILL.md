---
name: factory
description: Use the software factory to initialize a project, plan and approve issues, show the board, run tickets, verify a feature, or evaluate and learn from factory outcomes.
---

# Factory in Codex

Resolve this skill's physical path through any symbolic link. The factory checkout is three
directories above its containing directory. Run its `bin/factory` CLI from the target project's
root. Load only the matching `skills/<command>/SKILL.md` from the factory checkout.

- `$factory init` initializes the project.
- `$factory board [effort]` prints its issue board.
- `$factory feature <idea>` plans issues. Use `feature revise <effort> <change>` for revisions and
  `feature review <effort-or-issue>` to open pending Plannotator approval.
- `$factory feature-review <effort> [--implemented]` reviews a plan or verifies the current code.
- `$factory run [ticket]`, `learn [lesson]`, and `eval ...` use their corresponding workflows.

In shared instructions, replace the Claude plugin-root expression with the resolved checkout path.

## Role actions

For a `SPAWN` action, use the Codex subagent tool with a fresh context and the emitted prompt.
Give it the target project root and the emitted role's read/write scope. Only builders may edit
project code. Use an available Codex model or the user's model choice. Claude model names in the
action do not select a Codex model.

Track the run ID, result stem, and spawn number from the prompt header. Record each agent's full
final message unchanged with `factory record <run> <stem> <spawn>` on stdin, then advance the engine.
Follow its RUN, STOP, and IDLE actions. If agents are still working, wait for their Codex results
and record them first. A CLI wait cannot collect Codex results itself.

The shared result path also delivers UI tickets. Configure `review.ui_skill_file` to attach the
UI design skill to builder prompts; builders attest to the prompt digest as instructed there.
Native skill-tool transcript evidence remains supported.

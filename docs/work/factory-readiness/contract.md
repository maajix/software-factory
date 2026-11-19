# Factory readiness

The local Factory guides a new project from verified CI setup through an approved plan to a
tested delivery. The same tickets, approval records and gates work for any agent runner that can
execute the Factory CLI, run its prompts with the stated workspace scope, and return complete
results. Claude Code and Codex are existing integrations. A native hook may collect results, and
the CLI supports the same workflow through `factory record` for other runners. Model names in
actions are hints for runners that support them. Plan approval stays attached to the reviewed
Markdown revision.
Deliveries record the checked commits and review outcomes. A run that requires a rendered UI
proof stays blocked until that proof is available. A concrete browser check is enough for small
changes. Capture screenshots when acceptance depends on layout, responsive behavior, or another
visual difference the reviewer needs to inspect.

For learning, preserve the current rule unless an independent replay shows a better result at
the intended role boundary and preserves the passing cases. Save proposals for manual
evaluation when the project lacks a suitable replay.

## Proof

Use disposable repositories. Show CI hints matching the source workflow, a UI ticket delivered
through the shared CLI without a host hook, and paired baseline and candidate replays for
research and build behavior. Keep Claude Code's existing agent hooks and UI skill verification
working. Retain the human approval and backend delivery evidence from the existing Codex pilot.

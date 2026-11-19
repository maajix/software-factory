---
name: run
description: Drain the factory queue. Builds every open, unblocked implementation or task ticket in docs/issues through research, build, deterministic gates and fresh-context review, and leaves each one on a local branch with a PR text for the human. Use for "/factory:run", "run the factory", "work the queue", or to build one named ticket with the factory.
argument-hint: "[ticket path or effort/NN to start with]"
---

# Factory run

You are the orchestrator. The `factory` CLI decides every step; you execute exactly the action it
prints. You never write code, briefs, reviews, ticket edits or anything under `.factory/` yourself, and
you never judge an agent's result: the factory reads it.

CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory"`, run from the project root. If it exits non-zero, show
its message to the user and stop.

## Loop

1. Run `factory next` (in the first iteration add `--ticket "$ARGUMENTS"` when an argument was given).
   It prints one JSON action.
2. Execute it:
   - **SPAWN**: start every agent in `agents` with the Agent tool, passing `subagent_type`, `model`
     (only when the entry has one), `description` and `prompt` exactly as printed. Several agents: all at once, in parallel. An agent
     may return at once and keep working in the background; do not wait for it yourself, the factory
     waits for every result (its next action is a RUN of `factory wait`).
   - **RUN**: run `cmd` with Bash and `timeout` = `timeout_ms`. If it prints `RUNNING`, run it again.
     `factory wait` prints `RUNNING` followed by `<result>#<n>` for each result it still awaits. If the
     agent whose description ends in `(<result> #<n>)` has already ended (its result or its completion
     notice arrived), first pipe its complete final message into `factory record <run> <result> <n>` with
     a quoted heredoc (`<<'FACTORY_EOF'`).
   - **RECORD**: the factory did not capture an agent's result. Pipe that agent's complete final message,
     unchanged, into `cmd` with a quoted heredoc (`<<'FACTORY_EOF'`). If the agent returned nothing,
     skip this. Then continue.
   - **STOP**: tell the user the `reason` and stop. When it says the workspace changed while read-only
     agents ran, show the named paths and change nothing yourself.
   - **IDLE**: the queue is empty. Show `summary` and stop.
3. Go to 1. Do not ask the user anything between actions; the factory parks questions in the tickets.
   If an action carries a `note`, repeat it to the user in the report.

## Report

At the end, one line per run from `factory status`: ticket, outcome, branch. Name the tickets that now
wait for the human (`needs-info`, `needs-human`, `ready-for-review`).

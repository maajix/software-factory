---
name: learn
description: Show recurring failure signals or propose a role or skill lesson from user feedback. The factory can adopt a role lesson after independent replay. Use for "/factory:learn", when the user corrects a factory agent, or asks what the factory has learned.
argument-hint: "[lesson in the user's words, or empty to show signals]"
---

# Factory learn

CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory"`, run from the project root.

Use this skill after factory work when a user correction reveals a standing rule, or when repeated
successful use shows a procedure worth capturing. Keep the lesson short, name the behavior it should
change next time, and include a replayable example. Use [factory eval](../eval/SKILL.md) for changes
that require code or a new test.

- **No argument:** run `factory signals` and `git -C "${CLAUDE_PLUGIN_ROOT}" log --oneline -10 -- roles skills`.
  Report the pending signals and the last learned changes. Pending signals are handled automatically
  before the next ticket of `/factory:run`.
- **With a lesson:** run `factory learn --note "$ARGUMENTS"`. It prints a SPAWN action: start that
  agent with the Agent tool exactly as printed. Advance with `factory next --learn-only` and follow
  its SPAWN, RUN and RECORD actions until IDLE or STOP, using the same protocol as
  [factory run](../run/SKILL.md).
  Report whether the change was adopted, saved for replay, rejected, or unnecessary. On STOP, report the reason.

---
name: board
description: Show the factory's current issue board and what is waiting on plan approval or code review.
argument-hint: "[effort]"
---

# Factory board

Run `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory" board` from the project root. Pass the effort name
when the user wants one feature. Present the generated columns and issue links.

Each issue stays in its feature folder. Unfinished plans are in Draft. Finished plans that await
approval or need changes are in Plan review. Backlog issues are cleared for the queue and may wait
on dependencies. An implemented branch waiting on the owner is in Ready for code review. Done / closed
reflects the recorded ticket status. Show that status when a ticket was superseded or declined.

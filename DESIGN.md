# Software Factory design

The [CLI](bin/factory) manages state, executes configured gates, and emits actions for the
agent runner. Claude Code provides native hooks. Codex and other runners can use the shared
CLI to dispatch the prompts and record complete results.

## Plans and state

A project keeps its profile in `.factory/profile.json` and its tickets in a Markdown tracker.
The [ticket format](docs/TICKETS.md) defines effort folders, contracts, dependencies, and statuses.
Plannotator reviews finished ticket Markdown and its shared contract. The approval attaches
to their reviewed revisions. Contract changes hold affected work until the tickets are reconciled.

A project has one active run. Transitions lock project state while agents and gates work outside
that lock. Every agent result belongs to a specific run, result slot, and spawn. An interrupted
claim can resume from its stored revision. Build inputs changing during a gate invalidate that
gate evidence.

## Delivery

The researcher traces requirements through existing code. The builder works on a local Git
branch. Gates run at that checkout and independent reviewers assess the tested commits. A
delivery archives a PR draft and its evidence with the effort. UI reviews record browser
observations and retain screenshots when visual criteria need them.

A ticket can build on an unmerged reviewed dependency using the exact tested commit. If that
dependency is rejected or replaced, affected deliveries await reconciliation.

## Learning

Recurring failures or human feedback can start a read-only learner. The learner proposes one
instruction change. The Factory evaluates supported proposals on committed replay cases.
Researcher and reviewer replays score role decisions. Builder replays score patches in
separate disposable checkouts using independent executable acceptance checks.

A passing baseline skips the candidate. A candidate must improve a failed check while
preserving passing behavior. For qualified changes, adoption starts from the pinned Factory
commit and fast-forwards the unchanged installation. Proposals without a matching replay
remain available for manual evaluation.

See the [implementation boundaries](lib/factory/README.md) and the
[verification summary](docs/verification.md).

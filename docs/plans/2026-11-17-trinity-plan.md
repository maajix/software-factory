# Plan: EGM, Plumbline and the factory as one flow (2026-11-17)

Status: historical draft. The current direction is native factory commands and no dependency on
Plumbline. The owner chose to leave old Plumbline tickets outside the queue and park dependants if
an unmerged base is rejected. See [the updated workflow evidence](../research/08-feature-workflow.md).

## Decisions already made (by the user)

- **The factory is the hub; nothing is merged.** EGM stays an external, updatable plugin. Plumbline is the
  user's own repo (`maajix/Plumbline`) and is adapted where needed.
- **One ticket format** for every ticket, whatever made it.
- **A finished ticket's results live with its effort** in the issues folder; the bulky rest is deleted.
- **Ticket chains build on top of each other**: when 01 is delivered but not merged, 02 starts on 01's branch.

## Evidence

- EGM: all 7 skills set `disable-model-invocation: true`. A probe skill calling `egm:egm-draft` got "Ask the
  user to run /egm:egm-draft themselves" (`/tmp/sf2-probe/probe-x.jsonl`). The user types EGM commands.
- Plumbline: a factory skill loaded `plumbline:cut-slices` headless (same probe).
- Plugin `dependencies` exist in `plugin.json` with semver ranges; cross-marketplace needs
  `allowCrossMarketplaceDependenciesOn` (docs: code.claude.com/docs/en/plugins/dependencies.md).
- Prototype `/factory:slice` (`/tmp/sf2-proto`): a design doc became 4 tickets in the factory format with
  correct `Blocked by` and sizes (0.19 USD, 21 s). `factory queue` picked 01; the researcher read
  `spec.md` and the design doc; `DIFFICULTY: simple` put the builder on Sonnet (0.35 USD). The run
  stopped `needs-human` because `add` existed only on an unmerged branch: the chain problem below.
- After 01 is `ready-for-review`, `factory queue` is empty: 02-04 wait for a merge (checked).
- Preflight refused an uncommitted `docs/designs/`.
- The slice skipped Plumbline's cold-read and dropped `ID` and `Serves exit criterion`, which
  `write-spec`, `hold-the-line` and `cut-slices` read.
- Upstream: Pocock's current local tracker already uses the factory's layout
  (`<effort>/issues/NN-slug.md`, `Type:`, `ready-for-agent`, `needs-info`, `ready-for-human`).
  Osmani adds a task size XS-XL with "split at XL", checkpoints between ticket groups, and delta specs.

## Target flow

| Size   | Steps                                                                                                  |
|--------|--------------------------------------------------------------------------------------------------------|
| Large  | `/factory:feature` -> user runs `/egm:egm-brainstorm`, `/egm:egm-draft`, `/egm:egm-review` -> `docs/designs/<x>.md` -> `/factory:slice` -> `/factory:run` |
| Medium | `/factory:feature` -> factory calls Plumbline shape and spec (interactive) -> `/factory:slice` -> `/factory:run` |
| Small  | `/factory:feature` writes one ticket from the template -> `/factory:run`, or build it in the session |

## Work packages (one commit each, tests first, live check in a /tmp copy)

1. **Ticket format.** `docs/TICKETS.md` in the factory defines it: path `docs/issues/<effort>/issues/NN-slug.md`;
   header lines `Type`, `Status`, `Blocked by`, `Size` (XS, S, M, L; split above L), plus Plumbline's
   `ID` and `Serves exit criterion`; body sections What to build, Seams, Touches, Acceptance, Why.
   Statuses: `open`, `ready-for-agent`, `claimed`, `needs-info`, `ready-for-review`, `ready-for-human`,
   `resolved`, `declined`. In Plumbline (separate repo, separate PR): `cut-slices` writes this format and
   the status set gains the factory's words; old tickets stay readable.
2. **`/factory:slice <design doc|spec> <effort>`** from the prototype, keeping `ID`, `Serves exit
   criterion` and Plumbline's cold-read of the cut tickets. Writes `spec.md` with a `Design:` link. The
   design folder (`docs/designs/` by default) is excluded from the dirty check like the tracker root.
3. **Artifacts with the effort.** When a ticket run ends, the factory copies the keepers (brief, build result,
   review, security and UI results with their screenshots, gate summary without logs, `pr.md`, `run.json`)
   to `docs/issues/<effort>/runs/<NN>-<run id>/` and deletes `.factory/runs/<run id>`. Past runs (reopen,
   branch ownership, learner signals) are read from there. `verify/` logs are deleted once their baseline is
   in the profile; `hooks.log` rotates at 1 MB.
4. **Stacked chains.** A blocker in `ready-for-review` counts as done for building. The dependant's branch
   starts from the blocker's branch in every repo both touch; its review covers only its own commits;
   `pr.md` says "stacked on <branch>". Two unmerged blockers in one repo: start from the later one if it
   contains the other, else wait. A rejected blocker sends its delivered dependants to `ready-for-human`
   with "base ticket NN was rejected".
5. **`/factory:feature`** router: asks the size in one question with examples, then runs the row above.
6. **Dependencies.** `plugin.json` declares `plumbline` and `egm` once the factory is in a marketplace.

Order: 1, 2, 3, 4, 5, 6. Each package ends with the test suite green and one /tmp run.

## Open questions

- Package 4: a rejected 01 parks its dependants (proposal above), or rebuilds them automatically?
- Package 2: the cold-read costs one extra agent per slice. Always, or only for large features?
- Existing Plumbline tickets in the old layout: migrate once, or leave them unbuilt by the factory?

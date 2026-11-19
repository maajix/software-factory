# Factory

## Overview

The factory coordinates ticket and learning runs through a persisted state machine. The Python engine selects the next action and the orchestrator executes it.

## Interface

- `cli.main` receives commands from `bin/factory`. The plugin invokes `hooks.subagent_stop` to record agent results and `hooks.guard` on tool calls. [CLI](./cli.py), [hook handlers](./hooks.py), [hook registration](../../hooks/hooks.json)
- `next_action` advances or starts a run. `gate`, `wait_agents`, `record`, and `release` handle pending work. `feature_evidence` relates delivery evidence to the current contract and checkout. [Engine](./engine.py)
- `frontier` selects ready tickets, `contract_issues` detects stale revisions, and `plan` resolves reviewed dependency branches. [Tracker](./tracker.py), [Stack](./stack.py)
- `detect` gathers repository facts, `verify` establishes gate baselines, and `run_gate` executes checks. Shared filesystem and Git helpers live in `util.py`. [Discovery](./detect.py), [Profiles](./profile.py), [Gates](./gates.py), [Utilities](./util.py)
- `pending_signals` selects recurring problems for the learner. `report` and `ticket` turn observations into work for the factory's development checkout. [Signals](./signals.py), [Evaluation](./evaluate.py)
- `review` opens finished plans in Plannotator and publishes the approved revisions. `board` groups tickets by their workflow state. [Plan approval](./plans.py), [Engine](./engine.py)

## Invariants

- `state` names at most one active run. `next_action` returns one action while advancing or finishing that run.
- `state_lock` serializes run transitions, result updates and gate scheduling. Waiters release it between reads.
- A ticket claim starts with a saved run. `complete_claim` validates the original ticket and checkout before resuming it after an interruption.
- `result_path` requires the current spawn number and a matching SHA-256. `record` accepts results for pending spawns.
- `contract_issues` holds unfinished build tickets for an effort when their contract revision differs from the current contract. `plan` requires unmerged dependencies to retain their reviewed branch heads.
- A gate report records the checkout it tested. `gate_run` detects checkout changes during checks. `next_action` refreshes older evidence for a new clean revision before spawning reviewers.
- `advance_learn` requires an unchanged factory checkout and validates a proposal against independent replay cases before `adopt_candidate` can commit it.

## Side Effects

- Run state, prompts, results and gate reports are written under `.factory/`. Completed ticket runs are archived under the configured tracker. `set_status` and `comment` modify ticket files.
- `gate` starts a detached runner for the configured checks. Ticket runs can switch Git branches, and `adopt_candidate` can create and fast-forward a learning commit.
- `verify` stores gate baselines in the profile. `report` saves observations and `ticket` can create a ticket in a separate feedback checkout. Hooks may record results and restrict tool calls.

## Verification

- From the repository root, run `python3 -m unittest discover -s tests`.

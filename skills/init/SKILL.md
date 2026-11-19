---
name: init
description: Set the factory up in this repository. Explores the repo (submodules, stacks, CI, tracker, conventions), writes .factory/profile.json with verified gate commands, installs missing dependencies, and runs every gate once to record its baseline. Use for "/factory:init", "set up the factory here", or when factory commands say the profile is missing or out of date.
---

# Factory init

You set the factory up for this repository. Detect with the script, decide with judgment, prove every
command by running it. Write facts the scripts need, not prose the agents could read from the repo.

CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/bin/factory"`, run from the repository root (the parent repo when
there are submodules).

## 1. Detect

Run `factory detect`. It prints submodules, remote host, per-repo manifests and scripts, CI script
lines, tracker statistics, commit and merge conventions, tools on PATH and dirty repos. If a repo is
dirty, stop and tell the user: the factory works in this checkout and needs it clean.

## 2. Read what a script cannot judge

The root `CLAUDE.md`, `AGENTS.md`, `docs/agents/*.md`, the tracker README, and each repo's CI file. Use
them for: branch rule, commit rule, files the pipeline owns, which CI steps gate a pull request, which
need Docker or other services, and the ticket status vocabulary.

## 3. Write `.factory/profile.json`

```json
{
  "repos": [{"path": ".", "base": "main"}, {"path": "service-a", "base": "main"}],
  "setup": [{"id": "service-a:install", "repo": "service-a", "cmd": "pnpm install --frozen-lockfile"}],
  "gates": [
    {"id": "service-a:test-ci", "repo": "service-a", "cmd": "pnpm test:ci", "tier": "fast",
     "expect_tests": true, "timeout": 1800},
    {"id": "service-a:system", "repo": "service-a", "cmd": "pnpm test:system", "tier": "slow",
     "paths": ["src/*"], "requires": ["docker"], "expect_tests": true, "timeout": 3600}
  ],
  "tracker": {"type": "markdown", "root": "docs/work", "layout": "flat", "require_plan_review": true},
  "conventions": {"branch_regex": "^(bugfix/patch|feature/minor|feature/major)-[a-z0-9-]+$",
                  "commit_regex": "^(FEAT|FIX|UPT|DOCS|REFACTOR|TEST|CHORE): \\S",
                  "forbidden_paths": [".env.version"]},
  "review": {"security_paths": ["*auth*", "*token*", "*secret*"], "ui_paths": ["frontend/*"]},
  "tenant_data_allow": ["1.1.1.1", "8.8.8.8"],
  "rules": [],
  "inputs": {"service-a/package.json": null, "service-a/bitbucket-pipelines.yml": null}
}
```

Rules for filling it:

- **repos:** the parent and every checked-out submodule. `base` is the branch work starts from (the one
  the repo's CI releases from). It must resolve: check `git -C <repo> rev-parse --verify <base>`; use
  `origin/main` when there is no local `main`.
- **gates:** per repo, the commands CI runs on a pull request, in the same form (`pnpm test:ci` rather
  than its parts when CI runs the chain). `fast` = needs only the toolchain; always run. `slow` = needs
  Docker or services; give `requires` and the source `paths` that make it relevant. `expect_tests: true`
  for every command that runs tests, so a run with 0 tests fails. A repo without any gate gets none;
  report it.
- **setup:** install commands for repos whose dependencies are missing (`node_modules`, `.venv`), with
  the lockfile frozen.
- **tracker:** keep an existing factory profile's tracker settings. If detection found factory
  tickets in an existing tracker, use its root and layout. Otherwise use the flat tracker above.
  The built-in status and type defaults work for new projects. Require Plannotator approval for
  new trackers. Factory-authored plans also carry their own approval marker when using an older tracker.
- **conventions:** from CLAUDE.md and `git log`, not invented. `forbidden_paths`: files the pipeline
  owns (version files).
- **review.security_paths / ui_paths:** globs on repo-prefixed paths (`frontend/src/auth/*`).
- **rules:** only what an agent cannot learn from `CLAUDE.md` or the code. Usually empty.
- **inputs:** every manifest, lockfile and CI file the gates depend on (values `null`; verify fills
  hashes).

Write `.factory/.gitignore` covering `runs/`, `state.json`, `learn.json`, `hooks.log*`, `beat`, and
`verify/`, plus `evaluations/` for local observations. Init needs just this file and the profile under version control. Create the tracker
directory when the first ticket is written.

## 4. Verify

Every Bash call must finish within 10 minutes (timeout 600000), so verify in steps: first
`factory verify --setup-only` (installs), then `factory verify --no-setup --gate <id>` once per gate.
Each run stores the gate's baseline (status, test counts, seconds) in the profile. Failed commands
leave their logs in `.factory/verify/` for diagnosis.

- A gate that fails because the command is wrong (missing env, wrong directory, needs a service): fix
  the profile entry and rerun `factory verify --gate <id>`.
- A gate that is red on the base branch because the code is broken: set `"disabled": "red on base:
  <reason>"` on it, so the factory never asks a builder to fix unrelated failures, and report it.
- A slow gate whose requirement is missing stays in the profile (status `skipped`); report it.

## 5. Report

A table: gate, repo, status, tests, seconds. Then the facts that shape the factory (topology, host,
existing agent configuration or an explicit statement that none exists, branch and commit rules,
tracker, queue size from `factory queue`) and the blocked items with what
would unblock them.

# Software Factory

Software Factory gives coding agents a local workflow for turning approved plans into tested
changes. It plans work as Markdown tickets, runs the project's own checks, and keeps the evidence
with the delivery. It works with Claude Code, Codex, and other runners that can drive the Factory
CLI and return agent results.

## How it works

1. **Plan.** Describe a feature or fix. The Factory writes tickets with acceptance criteria and
   opens finished plans in Plannotator for approval.
2. **Build.** A researcher identifies the existing code, dependencies, and tests. A builder
   implements the ticket on a local branch.
3. **Verify.** The Factory runs the project's configured gates and sends the tested change to a
   fresh reviewer. UI work records a browser check, with screenshots when acceptance depends on
   a visual comparison.
4. **Learn.** Human feedback and recurring failures can produce proposed changes to agent
   instructions. The Factory adopts a proposal only when independent replay shows an improvement
   and preserves passing behavior.

Tickets, shared requirements, and run evidence are ordinary files in the project's checkout.
The Factory prepares a local branch and a pull request draft for each delivery.

## Install

You'll need Git, Python 3.10 or newer, and an agent runner. Install the
[Plannotator CLI](https://github.com/backnotprop/plannotator) for plan approval.

### Claude Code

In Claude Code, add the GitHub marketplace and install Factory.

```text
/plugin marketplace add https://github.com/maajix/software-factory.git
/plugin install factory@software-factory
```

The same install is available from the terminal.

```bash
claude plugin marketplace add https://github.com/maajix/software-factory.git
claude plugin install factory@software-factory --scope user
```

### Codex

Link the skill once, then open Codex in the project you want to work on.

```bash
git clone https://github.com/maajix/software-factory.git
factory_dir="$(cd software-factory && pwd)"
mkdir -p "$HOME/.agents/skills"
ln -s "$factory_dir/codex/skills/factory" "$HOME/.agents/skills/factory"
```

Use `$factory init`, `$factory feature`, and `$factory run` in place of the Claude Code
slash commands.

## Run your first feature

| Step | Claude Code command | What happens |
| --- | --- | --- |
| Initialize | `/factory:init` | Detect project conventions and verify the gates in `.factory/profile.json`. |
| Plan | `/factory:feature <idea>` | Write one or more tickets under `docs/work/` and open Plannotator. |
| Check the board | `/factory:board` | See which issues await approval, are in progress, or are ready for review. |
| Build | `/factory:run` | Work the approved queue and record checks and review for each delivery. |
| Verify the result | `/factory:feature-review <effort> --implemented` | Check the integrated behavior and save the evidence with the tickets. |

Use `/factory:feature revise <effort> <change>` when requirements change. The Factory tracks the
shared contract revision and holds affected tickets until their plans match it. Use
`/factory:learn` to see recurring signals and `/factory:eval` to capture a reproducible improvement.

## CLI and other runners

Use a local Factory clone as `factory_dir`, as in the Codex setup above.

```bash
"$factory_dir/bin/factory" --root /path/to/project detect
"$factory_dir/bin/factory" --root /path/to/project board
"$factory_dir/bin/factory" --help
```

The CLI exposes the same board, plan review, gates, and run state used by the built-in
integrations. Runners dispatch the actions from `factory next` and feed complete results back with
`factory record <run> <result> <spawn>` on standard input. The
[Codex skill](codex/skills/factory/SKILL.md) shows that protocol in use.

Project gates and Git conventions live in `.factory/profile.json`. If UI builders need the
`emil-design-eng` skill without a native skill tool, set `review.ui_skill_file` to its local
`SKILL.md`. Use `UI-Proof: screenshots` on a ticket when acceptance requires visual evidence.

## Development

Run the unit suite from the Factory checkout.

```bash
python3 -m unittest discover -s tests
```

Use a separate Factory checkout to run the queue when developing Factory itself. This keeps
the running engine stable while a builder changes its implementation. Automatic adoption of
an instruction also requires a clean Factory checkout.

- [Ticket format](docs/TICKETS.md)
- [Design](DESIGN.md)
- [Workflow research](docs/research/08-feature-workflow.md)
- [Readiness verification](docs/work/factory-readiness/verification.md)

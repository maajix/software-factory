# 03 Claude Code platform reference (for the software factory)

Checked 2026-11-16 against Claude Code **2.1.325** (`claude --help`, `plugin --help`, `plugin eval --help` from `~/.local/share/mise/installs/claude/2.1.325/claude`) and the code.claude.com docs, fetched as `.md` that day. No sessions were run, so runtime behaviour is as documented, not observed.

Markers: none = documented (and in `--help` where it is a flag). **[DOCS-ONLY]** = documented but missing from 2.1.325 `--help` (the string is in the binary, so likely a hidden flag). **[INFERENCE]** = my design conclusion, not a docs statement.

## 1. Plugins
Docs: https://code.claude.com/docs/en/plugins/manifest-reference.md, /plugins/components.md, /plugins/loading.md, /plugins/cli-reference.md

**Layout.** `.claude-plugin/plugin.json` is optional; only `name` is required (kebab-case, and a `claude-`/`anthropic-` prefix is an error). Everything else sits at the plugin root:
- `skills/<name>/SKILL.md`
- `commands/*.md` (legacy format)
- `agents/**/*.md`: scanned recursively, and each subfolder becomes a name segment (`plugin:sub:name`)
- `hooks/hooks.json`, wrapped in a top-level `"hooks"` key
- `.mcp.json` and `.lsp.json`
- `bin/`: added to the Bash tool's PATH after the user's own entries, so it can't shadow system commands
- `workflows/*.js`, `output-styles/`, `themes/`
- `monitors/monitors.json`: background commands whose output reaches Claude as notifications; they don't start with `-p`
- `evals/`

A root `CLAUDE.md` is **not loaded**, so put plugin instructions in skills.

**Manifest keys.** `skills` adds to the default directory. `commands`, `agents`, `outputStyles` and `workflows` replace theirs. `hooks`, `mcpServers` and `lspServers` merge. Paths must start with `./` and resolve inside the root: no `..`, and no symlink that points outside. `userConfig` values reach scripts as `CLAUDE_PLUGIN_OPTION_<KEY>`.

**Path variables.** These are substituted in skill, agent and command text, in hook, monitor, MCP and LSP configs, and exported to those processes:
- `${CLAUDE_PLUGIN_ROOT}`: the cache directory of the current version. It changes on every update, so don't write state there.
- `${CLAUDE_PLUGIN_DATA}`: `~/.claude/plugins/data/<id>/`. It survives updates.
- `${CLAUDE_PROJECT_DIR}`: the project root.

**Names.** Skills are `/plugin:skill`. MCP tools are `mcp__plugin_<plugin>_<server>__<tool>`. **Plugin agents ignore `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`.**

**Ways to load a plugin.**
- `--plugin-dir <dir|.zip|folder-of-plugins>` (repeatable), `--plugin-url`, or the `CLAUDE_CODE_PLUGIN_DIRS` env var. These load for the session only, as `name@inline`, and override an installed plugin of the same name.
- `~/.claude/skills/<name>/.claude-plugin/plugin.json` loads every session as `<name>@skills-dir`. `claude plugin init` creates one.
- The same layout under the project's `.claude/skills/` loads only after workspace trust, which **`-p` doesn't grant**. It loads only from the primary working directory, and its monitors are skipped.

**Marketplaces and installs.**
- A marketplace is `.claude-plugin/marketplace.json` with `{name, owner, plugins:[{name, source}]}`.
- Add one with `claude plugin marketplace add <owner/repo|git URL|URL|./path> --scope user|project|local`.
- Install with `claude plugin install name@mkt --scope ... [--json] [-y]`. To share with the team, use `--scope project` and commit `.claude/settings.json` (`enabledPlugins`, `extraKnownMarketplaces`).
- Other subcommands: `update`, `enable`/`disable`, `list --json`, `details` (projected token cost), `validate --strict`, `tag`, `prune`.

**Versioning.**
- The version comes from the manifest `version`, else the marketplace entry, else a 12-character git SHA. A local non-git directory gets `unknown`.
- A pinned `version` keeps users on it until the string changes.
- Each version is cached at `cache/<mkt>/<plugin>/<version>/`. Old copies are deleted 14 days after being orphaned.
- Auto-update is off by default for third-party marketplaces. A running session keeps its loaded version.
- **A relative-path plugin in a marketplace added from a local path loads in place.** Edits apply at the next session or `/reload-plugins`, with no version bump.

**When runtime edits take effect.**
- **Live-watched, no restart needed:** `SKILL.md` under `~/.claude/skills`, the project's `.claude/skills`, and `--add-dir` `.claude/skills` (not in `--bare`). Also `~/.claude/agents` and `.claude/agents`, if those directories existed at session start.
- **Plugin skills, agents, hooks and MCP servers are not watched.** They need `/reload-plugins`, which prints a `Reloaded:` line.
  - If the reload would change MCP tools, it refuses because the prompt cache would be invalidated; `--force` applies it anyway.
  - Under `-p` and the SDK (v2.1.260+), it runs only when typed into the prompt, and MCP servers don't reconnect.
  - The TypeScript SDK has `reloadPlugins({addPlugins})`.
- `/reload-skills` rescans skill, command and workflow directories, including ones created after session start.
- A SessionStart hook can return `reloadSkills:true` after it writes skills.
- An already-invoked skill isn't re-read. Re-invoking it with changed content appends the new version.
- **Conflict:** `plugin update --help` says "restart required"; the docs say `/reload-plugins` is enough.

**Where learned skills should live [INFERENCE].**
- Not in `${CLAUDE_PLUGIN_ROOT}`: it is a cache copy that updates replace.
- `${CLAUDE_PLUGIN_DATA}` survives updates, but it isn't a skill scan location, and manifest paths can't point outside the plugin root. Mounting a data subdirectory with `--add-dir` should load its `.claude/skills`, but I haven't tested that.
- Recommended split:
  - **Repo-specific learned skills** go in the project's `.claude/skills/<name>/` as plain skills, merged through the human-approved PR. They are live-reloaded and shared with the team.
  - **Don't add a `.claude-plugin/plugin.json` to them.** That turns the folder into a `<name>@skills-dir` plugin, which needs workspace trust (`-p` is not enough). Its components also get namespaced, and the docs don't say whether the folder still loads as a plain skill.
  - To eval one, stage it in a candidate plugin directory and run `claude plugin eval <dir>`, or point the case's `plugins:` entry at it. This path is untested.
  - **Improvements to the factory's own skills** are edits to the plugin's source repo, loaded in place, then tagged and versioned.

## 2. Skills
Docs: https://code.claude.com/docs/en/skills.md

**Frontmatter.** Every field is optional, and Claude Code silently ignores keys it doesn't recognise.

| Field | Effect |
|---|---|
| `name` | Defaults to the directory name. In a plugin it is prefixed with the plugin name |
| `description`, `when_to_use` | Drive automatic invocation. Combined, they are cut at 1,536 characters in the listing |
| `argument-hint`, `arguments` | Hint shown in autocomplete; named positional arguments for `$name` |
| `disable-model-invocation` | Only the user can invoke the skill, and it can't be preloaded into subagents |
| `user-invocable: false` | Only Claude can invoke the skill |
| `allowed-tools` | Pre-approves tools **for the invoking turn only**. It doesn't restrict anything |
| `disallowed-tools` | Removes tools while the skill is active |
| `model`, `effort` | Override for the rest of the turn, or for the fork |
| `context: fork`, `agent` | Runs the skill in a fresh subagent with **no conversation history**. `agent` picks the type (default `general-purpose`) |
| `background` | Fork only, default `true`. Under `-p` the fork always waits |
| `hooks` | Registered when the skill is invoked and kept for the rest of the session. Supports `once` |
| `paths` | Glob patterns. The skill auto-loads only when matching files are in play |
| `shell`, `metadata`, `license`, `compatibility` | Mostly informational |

**Substitutions.** `$ARGUMENTS`, `$N`, `$name`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, plus `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` in plugin skills. A `` !`cmd` `` line runs before Claude sees the skill.

**Progressive disclosure.**
- The listing of names and descriptions is always in context. Its budget is 1% of the context window (`skillListingBudgetFraction`); when it runs out, the least-used skills lose their descriptions.
- The body loads on invocation and then persists. Supporting files are read on demand, and scripts run without being loaded.
- Keep `SKILL.md` **under 500 lines**.
- After compaction, the most recent invocation of each skill is re-attached: up to 5,000 tokens each, 25,000 tokens total.

**Locations and precedence.**
- Enterprise beats personal (`~/.claude/skills`), which beats project (`.claude/skills`, searched from the start directory up to the repo root; nested skills load on demand).
- Plugin skills are namespaced, so they never clash.
- `skillOverrides` doesn't apply to plugin skills.

**Security:** a project skill's `allowed-tools` is honoured even in an untrusted `-p` run. A skill the factory writes can therefore grant itself tools, so review every skill diff.

## 3. Subagents and teams
Docs: https://code.claude.com/docs/en/sub-agents.md, /agent-teams.md, /worktrees.md

**Scopes, highest priority first:** managed, then `--agents` JSON (a file path is accepted with `-p`), then `.claude/agents`, then `~/.claude/agents`, then plugin `agents/`.

**Frontmatter** (camelCase):
- `name`: required, at most 256 characters, no `:`.
- `description`: required.
- `tools`, `disallowedTools`.
- `model`: `sonnet`, `opus`, `haiku`, `fable`, a full ID, or `inherit`.
- `permissionMode`: ignored when the parent runs in bypass, acceptEdits or auto mode.
- `maxTurns`: at the limit, output is marked partial and the agent can be resumed.
- `skills`: preloads full skill content, at most 32 skills.
- `mcpServers`.
- `hooks`: a `Stop` hook here runs as `SubagentStop`.
- `memory`: `user`, `project` or `local`.
- `background`, `omitClaudeMd`, `effort`, `autoCompactWindow`, `initialPrompt`, `color`.
- `isolation: worktree`: the agent works in a temporary worktree under `.claude/worktrees/`. It branches from the remote **default branch** unless `worktree.baseRef:"head"` is set. The worktree is removed if nothing changed and kept otherwise. Git commands aimed at the main checkout are blocked.

**Agent memory.**
- Locations: `~/.claude/agent-memory/<name>/`, `.claude/agent-memory/<name>/` (the recommended scope), or `.claude/agent-memory-local/<name>/`.
- The first 200 lines or 25 KB of `MEMORY.md` are injected, and Read/Write/Edit are enabled automatically.
- Turning off auto memory turns agent memory off too.

**Startup context.** Each subagent gets its own system prompt (not Claude Code's), the delegation message, the CLAUDE.md files (Explore, Plan and `omitClaudeMd` agents skip them), git status and its preloaded skills. It does not get the parent's history or auto memory.

**Results.**
- The final message returns to the caller: as the tool result for a foreground agent, or as a notification for a background one. Background is the default from the main session.
- The returned agent ID lets the caller continue with `SendMessage{to: id|name}`, which keeps the agent's full history.
- Transcripts live at `<session>/subagents/agent-<id>.jsonl`.
- Nesting goes 3 levels deep, with at most 20 concurrent agents (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`).
- **Subagents never get the `Workflow`, `AskUserQuestion` or `EnterPlanMode` tools.**

**Agent teams** (experimental, enabled with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`).
- A lead session plus teammate sessions share a task list (`~/.claude/tasks/<team>/`, with dependencies and file locking) and mailboxes.
- One team per session, no nested teams, and teammates aren't restored on resume.
- **Teammates are not spawned under `-p` or the SDK.**
- Quality gates come from the `TeammateIdle`, `TaskCreated` and `TaskCompleted` hooks.
- `SendMessage` also reaches your other sessions, no team needed (cross-session messaging, v2.1.224+).

## 4. Hooks
Docs: https://code.claude.com/docs/en/hooks.md

**Shape and sources.** `{"hooks":{Event:[{"matcher":"...","hooks":[handler]}]}}`. Hooks can come from settings files (user, project, local, managed), a plugin's `hooks/hooks.json`, skill frontmatter (active after invocation) and agent frontmatter (active while the agent runs). Settings and plugin hooks also fire inside subagents, with `agent_id` and `agent_type` set.

**Handler types.**
- `command`: JSON on stdin. Supports `args` (exec form), `async`, `asyncRewake` and `onFailure:"block"`.
- `http`.
- `mcp_tool`.
- `prompt`: a single LLM call returning `{ok,reason,impossible}`. Default timeout 30 s.
- `agent` (experimental): a subagent with Read/Grep/Glob for up to 50 turns. Default timeout 60 s.

Common fields: `if` (permission-rule syntax, tool events only), `timeout` (600 s for command hooks), `once` (skills only).

**Common input fields.** `session_id`, `prompt_id` (matches the OTel `prompt.id`), `transcript_path`, `cwd`, `permission_mode` (Manual mode arrives as `"default"`), `effort`, `hook_event_name`, `agent_id`, `agent_type`.

**Exit codes.**
- `0`: success. Stdout is parsed as JSON only if it contains nothing else.
- `2`: block. Stderr becomes the reason.
- Anything else: a **non-blocking** error, and the action proceeds.

JSON output can also carry `continue:false` with `stopReason`, and `systemMessage`. Each string is capped at 10,000 characters.

| Event | Blocks | Key input | Control |
|---|---|---|---|
| SessionStart | no | `source` (startup, resume, clear, compact, fork), `model` | `additionalContext`, `initialUserMessage` (-p), `sessionTitle`, `watchPaths`, `reloadSkills`. Command and mcp_tool handlers only |
| UserPromptSubmit | yes | `prompt` | `decision:"block"`, `additionalContext` |
| PreToolUse | yes | `tool_name`, `tool_input` | `permissionDecision` allow/deny/ask/defer, `updatedInput`, `additionalContext` |
| PermissionRequest | JSON only | tool call | `decision.behavior` allow/deny |
| PostToolUse | no | `tool_response`, `duration_ms` | `decision:"block"` sends feedback; `updatedToolOutput` |
| PostToolBatch | yes | the batch | Stops before the next model call |
| SubagentStart | no | `agent_id`, `agent_type` | `additionalContext` |
| SubagentStop | yes | `last_assistant_message`, `agent_transcript_path`, `stop_hook_active` | `decision:"block"` makes the reason the subagent's next instruction |
| TaskCreated, TaskCompleted | yes | `task_id`, `task_subject`, `teammate_name` | Exit 2 or `decision:"block"` |
| Stop | yes | `stop_hook_active`, `last_assistant_message`, `background_tasks` | `decision:"block"` with `reason` keeps working. Capped at 8 blocks in a row |
| TeammateIdle | yes | `teammate_name` | Exit 2 keeps the teammate working |
| PreCompact | yes | `trigger` | Stdout becomes compaction instructions |
| SessionEnd | no | `reason` | **1.5 s budget; plugin hook timeouts don't extend it** |

Other events: Setup (run with `--init`, `--init-only` or `--maintenance` [DOCS-ONLY]), StopFailure, PostToolUseFailure, PermissionDenied, InstructionsLoaded, ConfigChange, CwdChanged, FileChanged, WorktreeCreate, WorktreeRemove, PreModelSwitch, PostModelSwitch, Notification, Elicitation.

Prompt and agent handlers work on tool, stop, task, teammate and prompt events, but not on SessionStart, SessionEnd, PreCompact or SubagentStart.

**Recipes.**
- Block a tool: PreToolUse that exits 2 or returns `deny`.
- Force continuation: Stop or SubagentStop with `decision:"block"`. Check `stop_hook_active` to avoid loops.
- Pass a subagent's result to the parent: PostToolUse with matcher `Agent`.
- `/goal` is implemented as a session-scoped prompt Stop hook.

## 5. Automation
Docs: https://code.claude.com/docs/en/headless.md, /cli-reference.md, /agent-sdk/overview.md, /github-actions.md, /routines.md, /scheduled-tasks.md, /workflows.md

**`claude -p` flags.**
- Output: `--output-format text|json|stream-json`. JSON carries `result`, `session_id` and `total_cost_usd`. Stream-json needs `--verbose` and ends with a `result` message. Related: `--include-partial-messages`, `--include-hook-events`, `--forward-subagent-text`, `--input-format stream-json`.
- `--json-schema`: the result lands in `structured_output`. The field can be missing, so check for it.
- Limits: `--max-turns` [DOCS-ONLY], `--max-budget-usd`.
- Permissions: `--permission-mode acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`, `--permission-prompts none`, `--permission-prompt-tool`, `--allowedTools`/`--disallowedTools "Bash(git *)"`, `--tools`.
- System prompt: `--append-system-prompt`, `--system-prompt`; the `-file` variants and `--append-subagent-system-prompt` are [DOCS-ONLY].
- Sessions: `--resume <id|name|path.jsonl>`, `--fork-session`, `--session-id`, `--no-session-persistence`.
- Configuration: `--plugin-dir`, `--agents`, `--agent`, `--model`, `--effort`, `--settings`, `--setting-sources`, `--mcp-config`, `--strict-mcp-config`, `--add-dir`, `-w`.
- `--bare` skips hooks, plugins, skills, CLAUDE.md and memory. It is **slated to become the `-p` default**, so pass `--plugin-dir` explicitly.
- `--bg` runs a background session, managed with `claude agents|attach|logs|stop`.
- The `system/init` event lists `plugins`, `plugin_errors` and `mcp_server_errors`, which makes a good CI gate.
- What `-p` changes: it skips the trust dialog, so project hooks and `.mcp.json` run. It has no team spawning, no `/plugin`, no monitors and no trust-gated repo plugins. Workflows and `/goal` work.

**Agent SDK** (`claude-agent-sdk`, `@anthropic-ai/claude-agent-sdk`).
- It runs the Claude Code binary: same tools, subagents and sessions.
- Hooks are callbacks, and `canUseTool` decides permissions.
- Load plugins with `plugins:[{type:"local",path}]`.
- `settingSources` defaults to user, project and local; pass `[]` for isolation.
- `listSessions()` and `getSessionMessages()` read sessions, and a `SessionStore` adapter persists them.
- Authenticate with an API key: products built on the SDK may not offer claude.ai login.
- Best fit for an **external orchestrator daemon**.

**GitHub Actions.** `anthropics/claude-code-action@v1`, set up with `/install-github-app`. Inputs include `prompt`, `claude_args`, `plugin_marketplaces` and `plugins`. Triggers are `@claude` mentions or any event, including cron.

**Cloud scheduled tasks** (formerly routines, research preview). Triggers: a schedule (at most hourly), API `POST .../fire` with a bearer token, or a GitHub PR, release or issue event. Runs use auto mode on a fresh clone, **without `~/.claude/skills`**, and are limited to 100 runs/hour. Create them with `/schedule`.

**In-session repetition.** `/loop`: minimum 1-minute interval, needs an open session, expires after 7 days. `/goal <condition>`: keeps taking turns until a model judges the condition met. It works with `-p`.

**Workflow tool.**
- A JS script: `export const meta={name,description}`, then calls to `agent(prompt,{schema,label})`, `pipeline()`, `parallel()`, `phase()` and `log()`. Input arrives in the `args` global.
- Runs in the background and is resumable within the session.
- Up to 16 concurrent agents (raise to 256 with `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`), 1,000 agents per run, 4,096 items per call.
- Restrictions: no user input mid-run, no filesystem, shell or `import()` from the script itself, and `Date.now`/`Math.random` throw.
- Save to `.claude/workflows/` or a plugin's `workflows/`.
- Works under `-p` and the SDK. **It can't be called from subagents.**

**Fit [INFERENCE].** Use Workflow for deterministic fan-out. Use the main session plus subagents when each step needs judgment. Use the SDK, Actions or cloud tasks for unattended triggers. Put gates in hooks.

## 6. Evaluation
Docs: https://code.claude.com/docs/en/plugin-evals.md, /skills.md#evaluate-and-iterate-on-a-skill

**`claude plugin eval [target]`** (docs: v2.1.269+). Targets: a plugin directory, a single case file, `name@mkt` or `name@skills-dir`.

**Case format.**
- Each case is `evals/<case>/prompt.md`. Its frontmatter takes `runs` (default 3), `max_turns` (10), `timeout_seconds` (300), `allowed_tools`, `model`, `tags`, `plugins` and `env` (`EVAL_*` keys only).
- Graders live in `graders/*.md`.
- An optional `case.yaml` adds `scaffold_script` (requires `--scaffold`), `history_file` and `add_dirs`.
- MCP mocks go in `mocks/<server>/<tool>.md`.

**Graders.**
- Free: `regex`, `tool_used` (`tool: Skill` checks that a skill fired), `tool_order`, `file_exists`.
- Judged by a model: `llm` (2 of 3 votes), `baseline`.
- **There are no custom-code graders.**

**Scoring.**
- A case's score is the mean, over runs, of the weighted pass fraction.
- When a plugin resolves, `--ablation` defaults to `with-without`: each case also runs the same number of times without the plugin, and the report shows the difference (Δ). **Δ never affects the exit code**; only the with-arm score is compared to the threshold.
- In a two-arm run, graders that can't pass without the plugin (such as `tool_used: Skill`) become unscored indicators (`scored: false`) unless you set `arm: both`. A "skill fired" gate therefore needs `--ablation none` or `arm: both`.
- The default threshold is **1.0**.
- Exit codes: 0 pass, 1 fail, 2 partial (cost cap hit or auth failure), 130 interrupted, 143 terminated.
- Output: `results/<ts>/aggregate-result.json` and `report.html`.

**Sandbox.** Each run gets a temporary HOME, working directory and config, and runs as a `claude -p` child with **only the plugin loaded**. No user or project config and no CLAUDE.md load. Case files are hidden from the agent. Network access is not sandboxed outside shell commands.

**CI invocation:** `claude plugin eval . --trust-plugin --json r.json --threshold 0.8 --model M --judge-model M --no-publish --max-cost-usd 20`. Other options: `-j 1..8`, `--ablation none`, `--allow-tools`.

**Conflicts between sources.** For the default judge model, `plugin eval --help` says `haiku` while the docs page says "the model for background tasks". The docs require v2.1.269+, while older notes said 2.1.198.

**`/skill-doctor`** (v2.1.252+, needs feature-flag fetching). Reports per-skill context cost, uses, never-invoked skills and unused plugins. It is not a linter: use `plugin validate` for that.

**skill-creator plugin.** Keeps cases in `evals/evals.json` and runs one subagent per case. Writes `grading.json` and `benchmark.json` (pass rate, time and tokens, with vs without the skill). It can run a **blind A/B between two skill versions** and tune descriptions for trigger rate. Its format is separate from plugin eval's.

**Gating self-modification [INFERENCE].** Plugin eval only compares with vs without the plugin. To compare two versions, run the suite on both directories and diff the results, or use skill-creator's A/B.

## 7. Memory
Docs: https://code.claude.com/docs/en/memory.md

**CLAUDE.md files, in load order.** Managed (`/etc/claude-code/CLAUDE.md`), then user (`~/.claude/CLAUDE.md`), then project (`./CLAUDE.md` or `./.claude/CLAUDE.md`), then `./CLAUDE.local.md`. Files in ancestor directories load at launch and are concatenated; files in subdirectories load on demand. Files over 4 MiB are skipped. `AGENTS.md` is also supported.

**`@path` imports.** Paths resolve relative to the importing file, up to 4 hops deep. External imports in a project file need approval.

**`.claude/rules/*.md`.** Rules always load, unless `paths:` globs restrict them to matching files touched by Read, Write or Edit. User-level rules go in `~/.claude/rules/`.

**Auto memory.** Stored in `~/.claude/projects/<repo>/memory/`. `MEMORY.md` is the index (first 200 lines or 25 KB load); topic files are read on demand. It is machine-local, shared across worktrees, and not given to subagents. Off switches: `autoMemoryEnabled`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`.

**`/init`** writes a starter CLAUDE.md with build/test commands and conventions, or suggests improvements to an existing one. With `CLAUDE_CODE_NEW_INIT=1` it also offers to set up skills and hooks.

## 8. Session data and telemetry
Docs: https://code.claude.com/docs/en/sessions.md, /costs.md, /monitoring-usage.md, /analytics.md

**Transcripts.** Stored at `~/.claude/projects/<cwd with non-alphanumerics replaced by '-'>/<session-id>.jsonl`, with subagents under `<session>/subagents/`. The docs say **"The entry format is internal to Claude Code and changes between versions."** Retention is 30 days (`cleanupPeriodDays`), and the files aren't encrypted.

**Supported ways to read sessions:** `/export`, `claude -p --resume <id> --output-format json`, hook payloads (`transcript_path`, `last_assistant_message`), stream-json, and the SDK's `getSessionMessages`.

**Usage reports.** `/insights` writes an HTML report to `~/.claude/usage-data/report.html` covering up to 200 new sessions per run, including friction points; it consumes tokens. `/usage` shows usage, and `/team-onboarding` also uses session history.

**OpenTelemetry.** Enable with `CLAUDE_CODE_ENABLE_TELEMETRY=1` plus `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER` and an OTLP endpoint.
- Metrics include `claude_code.cost.usage`, `token.usage`, `commit.count`, `pull_request.count`, `lines_of_code.count` and `active_time.total`.
- Events include `api_request`, `tool_result`, `tool_decision`, hook execution and `skill_activated`. The skill name in `skill_activated` is redacted unless `OTEL_LOG_TOOL_DETAILS=1`.
- Traces are in beta (`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`). In `-p` runs, Claude Code honours an inbound `TRACEPARENT`.

**Cost.** `total_cost_usd` in `-p` JSON output is a client-side estimate. Dashboards: claude.ai/analytics/claude-code and platform.claude.com/claude-code.

## Design implications [INFERENCE]
- **Orchestrate from the main session or the SDK.** Subagents lack Workflow and AskUserQuestion, and agent teams don't run headless.
- **Run builders with `isolation: worktree`** and choose `worktree.baseRef` explicitly.
- **Put gates in plugin-level hooks filtered on `agent_type`**, because plugin agents drop `hooks` and `permissionMode`. Examples: Stop/SubagentStop for "tests pass", PreToolUse to block pushes to main.
- **Record learning signals in PostToolUse, Stop and SubagentStop hooks**, writing to `${CLAUDE_PLUGIN_DATA}`. Avoid SessionEnd, which only gets 1.5 s.
- **Loop:** propose a skill diff, eval it as a candidate plugin directory, open a PR, merge. Watched skill directories pick the change up live; plugin changes need `/reload-plugins` or a new session.

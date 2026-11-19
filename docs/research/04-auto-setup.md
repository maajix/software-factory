# 04: Agents that set themselves up in an unfamiliar repo (state at 2026-11-16)

Scope: evidence for the "init" step of a Claude Code based factory dropped into an unknown repository. Conventions: `[n]` cites the numbered source list at the end. Quotes are verbatim from pages fetched on 2026-11-16. arXiv dates are v1, plus the version quoted. Product docs carry no date ("undated living doc, fetched 2026-11-16"). UNVERIFIED marks claims without a captured verbatim quote.

## 1. Environment-setup agents and benchmarks

All run the same loop (read docs, run commands in a container, read errors, retry). The success oracle differs, and matters more than headline numbers.

| System | Mechanism | Result |
|---|---|---|
| ExecutionAgent [2] (ISSTA'25) | Shell agent plus "meta-prompting to gather guidelines" | "executes the test suites of 33/50 projects"; "deviation of only 7.5%" from ground-truth test results; "74 minutes and LLM costs of USD 0.16, on average per project" |
| Installamatic [5] | Dockerfile from "searching for relevant instructions from documentation" | "55% ... installed by our agent at least one out of ten times" (40 Python repos) |
| Repo2Run [1] | Iterative Docker build plus test runs that yield a Dockerfile (UNVERIFIED, paraphrase of abstract) | 420 Python repos with tests: "achieves an 86.0% success rate, outperforming the best baseline by 63.9%" |
| EnvBench [4] | Hard repos only, "excluding projects that can be fully configured by simple deterministic scripts" | GPT-4o best: "6.69% repositories for Python and 29.47% repositories for JVM"; oracle: "static analysis check for missing imports" / "compilation check" |
| SetupBench [3] | 93 bare-sandbox tasks, OpenHands | "repository setup (38.9-57.4%) and local database configuration (20.0-53.3%)"; "38-89% of actions being unnecessary"; failures: "incomplete development tooling installation, hallucinated task constraints" |
| CompileAgent [6] (ACL'25) | Tool agent, C/C++ | "improves the compilation success rate, ranging from 10% to 71%" (gain, absolute rate UNVERIFIED) |
| SWE-smith [7] | SWE-agent told "to install the codebase and run the test suite"; accept if "more than 80% of existing tests pass" (page renders "8080%") | Human converts trajectory to Dockerfile, "∼7 min per repository" |
| SWE-bench-Live [8] | "automated curation pipeline ... from instance creation to environment setup" | No build rate in abstract |
| RepoLaunch [9] (2026) | "resolves dependencies, compiles source code, and extracts test results" | "78% build success rate, outperforming the Python/Linux-only prior system by 18%" |
| Multi-Docker-Eval [10] | 40 repos, 9 languages | "environment construction being the primary bottleneck"; "model size and reasoning length are not decisive factors" |
| EvoConfig [11] (2026) | Multi-agent, "expert diagnosis module for fine-grained post-execution analysis" | "a 78.1% success rate" on EnvBench; gap versus [4] unexplained, comparability UNVERIFIED |
| DeployBench [12] (2026) | Research-artifact deployment, OpenHands | "pass-rates from 7.8%-51.0%"; "Failures are dominated by a completion-judgment problem" (102/181 self-stops; "pre-finish checks validate a different or weaker target") |
| ResearchEnvBench [13] (2026) | Research repos; pass if env "successfully executes at runtime" | Failures from "incomplete dependency resolution and brittle version coupling"; no numbers in the abstract |

Takeaways: (a) rows are not comparable: oracle (import/compile [4], tests [2][7], real workload [12]), repo selection and model all differ. (b) The dominant 2026 failure is declaring done on a weaker check [12][3]. (c) Environment changes may not persist (UNVERIFIED paraphrase of [3]).

## 2. Products

- **Claude Code /init** [14]: "Claude analyzes your codebase and creates a file with build commands, test instructions, and project conventions it discovers"; on an existing file it "suggests improvements rather than overwriting it". With `CLAUDE_CODE_NEW_INIT=1` it "explores your codebase with a subagent, fills in gaps via follow-up questions, and presents a reviewable proposal before writing any files" (CLAUDE.md, skills, hooks). Guidance: "target under 200 lines per CLAUDE.md file"; `/doctor` "cuts content Claude can derive from the codebase, such as directory layouts, dependency lists, and architecture overviews".
- **Codex cloud** [16]: "Codex can automatically install dependencies and tools" (common package managers); optional setup and maintenance scripts; "caches container state for up to 12 hours"; "If your repo includes `AGENTS.md`, the agent uses it to find project-specific lint and test commands"; agent-phase internet "off by default". Setup-script exports do not reach the agent phase (UNVERIFIED paraphrase of [16]). AGENTS.md is "used by over 60k open-source projects" [17].
- **Factory Agent Readiness**: launch post [18] (2026-01-20): "eight technical pillars and five maturity levels"; remediation "spins up an agent that opens a pull request to fix failing criteria"; "Level 3 is the target." Current docs [19] list nine pillars (Style & Validation, Build System, Testing, Documentation, Development Environment, Debugging & Observability, Security, Task Discovery, Product & Experimentation), levels Functional, Documented, Standardized, Optimized, Autonomous, and "To unlock a level, you must pass 80% of the criteria from the previous level." Sources disagree on pillar count; no outcome data links level to agent success.
- **Devin** [20][21]: "inspects your codebase and figures out which tools, runtimes, and dependencies it needs", "proposes a blueprint as suggestion cards", then "runs a build from the approved blueprint and produces the snapshot that every session boots from"; "it cannot discover your credentials". Knowledge is generated "based on the existing READMEs" and pulled from "specialized files" (`CLAUDE.md`, `AGENTS.md`); Knowledge is being migrated to Skills (UNVERIFIED paraphrase of [21]).
- **Copilot cloud agent** [22][23]: otherwise it installs deps "via a process of trial and error". `copilot-setup-steps.yml`: "The job MUST be called `copilot-setup-steps`"; only `steps`, `permissions`, `runs-on`, `services`, `snapshot`, `timeout-minutes` ("maximum value: `59`") count; on a failing step it "will skip the remaining setup steps"; template triggers to "Automatically run the setup steps when they are changed". Instruction files can be agent-generated ("ask Copilot cloud agent to generate one for you"), covering "continuous integration builds" and telling the agent to "trust the instructions".
- **Jules** [24]: "studies your repository to learn how to quickly setup your environment without a provided setup script", refers "to agents.md or your readme.md"; "Run and Snapshot" validates the script, snapshot reused "for future Jules tasks".
- **Cursor** [25]: rules "Stored in `.cursor/rules`" (always, glob, agent-decided, manual); "Keep rules under 500 lines"; "`/create-rule` in Agent"; "Cursor supports AGENTS.md".

Pattern: products split a reproducible **environment** (script, snapshot, image) validated by running it from a short **instruction file** converging on AGENTS.md.

## 3. Evidence on context files

**Gloaguen et al. [26]** (main controlled study): four agents, SWE-bench plus CTXbench (138 instances, 12 repos with developer files). Generated files used "the recommended initialization command and model for each agent individually".
- Success: "does not generally improve task success rates"; "LLM-generated context files cause performance drops in 5 out of 8 settings"; developer files "improve performance for all agents but Claude Code". **Claude Code (Sonnet-4.5), CTXbench table values: 73.2% none / 65.2% generated / 70.3% developer.**
- Cost: "cost increase of 20% and 23% on average" (p < 0.001%); context "significantly increases the number of tests run".
- Hurts: "context files are not effective at providing a repository overview" (no fewer steps to relevant files).
- Followed: "instructions in context files are well followed"; "uv is used 1.6 times per instance on average when mentioned". Steering tool choice is shown; a success gain from commands is **not**.
- Redundancy: with docs removed, generated files "consistently improve performance by 2.7% on average". Advice: only what is "not already present in the README"; useful "for specifying non-standard coding practices".

**Weaker evidence:**
- Lulla et al. [27] (10 repos, 124 PRs: UNVERIFIED; agent unnamed): "lower median runtime" (-28.64%), "reduced output token consumption" (-16.58%), "comparable task completion behavior". Conflicts with [26] on cost; candidate reasons (human vs generated files, runtime vs dollars) untested.
- Khatri [29] (small n): "Context strategy does not measurably move correctness on either agent"; failures are "implementation skill".
- McMillan [30]: "file-structure variables did not produce detectable contrasts" (null, small).
- Vercel [31] (vendor, one framework): 8KB version-matched docs index in AGENTS.md "achieved a 100% pass rate" vs 53% skills default.
- Agent READMEs [28] (2,303 files, UNVERIFIED count): "evolve like configuration code through frequent, small additions"; "security (14.8%) and performance (14.5%) are rarely specified".
- GitHub [32] (qualitative): "Put relevant executable commands in an early section"; "always do, ask first, never do".
- Anthropic [15]: "Only write down what Claude can't find by reading the repo"; "If both are yes, leave it out"; no-exception rules: "make it a hook, a deny rule, or a managed setting."

Net: generated overviews cost ~20% and can lower success; gains come from what the agent cannot derive (non-standard tools, version-specific APIs, gotchas, sparse-doc repos).

## 4. Convention mining

- **Cursor Bugbot** [33] (2026-04-08): candidate rules from reactions, replies, human review comments; it will "promote a candidate rule to active status" and "can disable it" on negative signal. Resolution rate "nearing 80%", not attributed to learning.
- **CodeRabbit** [34]: learnings from PR comments, `local`/`global` scope; optional approval "creates a pending request instead of immediately adding the learning"; formal standards belong in "review instructions or coding guidelines" (auto-read from `CLAUDE.md` etc.).
- **Greptile** [35]: "automatically infers custom rules from team behavior", checks "which comments get addressed"; "Week 5-8: Custom patterns emerge".
- **Graphite** [36]: "Learns from feedback"; mechanism undocumented.
- **CLAUDE.md from review**: add when "A code review catches something Claude should have known about this codebase" [14]; Anthropic teams keep "a `CLAUDE.md` in git to document mistakes" (InfoQ, secondary [37]).
- **Developer sessions**: Claude Code auto memory is "notes Claude writes itself based on your corrections and preferences", loaded each session ("first 200 lines or 25KB") [14]. No outcome data.
- **Research**: [38] codifies "every accepted review comment ... as a persistent behavioral rule" (5 to 18 rules, 0% recurrence in 11 sessions, no control). [39]: of 31,073 CodeRabbit comments "56.3% were rejected"; raw review signal needs filtering.

## 5. Synthesis: recommended init procedure (inference from cited evidence)

**Detect, deterministic first.** Manifests and lockfiles, task runners, CI workflows (inference: strongest evidence of real commands; [23] asks for CI in instructions), lint/format/type and pre-commit configs, Docker/devcontainer/compose, `.env.example`, existing AGENTS.md/CLAUDE.md/`.cursor/rules`/Copilot instructions. Common package managers are scriptable [16][4]; use the agent loop only for the rest. Credentials cannot be inferred [20]: emit a BLOCKED item naming the variables.

**Verify each command against the real target.**
1. Fresh shell, clean worktree: state may not persist [3][16]; "gitignored files like `.env` aren't there and dependencies aren't installed" [15].
2. Record exit code, duration, test counts; 0 tests run = fail (weak-proxy checks dominate failures [12]).
3. Store a baseline, not "all green": SWE-smith accepts >80% [7], ExecutionAgent compares to ground truth [2]; compare with the latest CI run.
4. Lint/typecheck must fail on a seeded violation, then revert.
5. Cap time and steps [2][3].

**Write, small and split by kind.** Canonical root AGENTS.md plus a CLAUDE.md that imports it: with both present Claude reads "Your `CLAUDE.md` files only", any CLAUDE.md or CLAUDE.local.md "in your working directory or above it" suppresses AGENTS.md (nested repos!), and where AGENTS.md is unsupported docs say "import it from a `CLAUDE.md`" [14]. Under 200 lines [14]: verified commands first [32], non-default conventions/tools [26], gotchas, never/ask-first boundaries [32]; no overviews, trees, dependency lists [14][26]. Hard gates as hooks [15]. Path-scoped rules per subproject [14][25]. One idempotent setup script reusable for Codex, Copilot steps, devcontainer [16][22]. A machine-readable manifest (commands, baselines, CI-job mapping, input hashes): factory design, unsourced. Everything proposed as a reviewable diff [14].

**Keep fresh.** Hash inputs (manifests, lockfiles, CI, tool configs); on change re-verify and re-propose, as Codex invalidates caches [16] and Copilot re-runs changed setup [22]. Periodic `/doctor prompt-audit` for "references to files or commands that don't exist" [14]; nightly command smoke run. Review comments become *candidate* rules needing repeated signal plus approval [33][34], disabled on negative signal [33].

**Measure.** (1) Share of commands verified and baseline agreement with CI. (2) A/B on 10-20 held-out historical tasks with and without generated files, measuring success, cost, steps as in [26]; expect ~zero success effect [26][29], accept if cost does not rise and instructions are followed. (3) Readiness checklist after [19], secondary. (4) Recurrence of review-flagged error classes [38].

## Sources

1. https://arxiv.org/abs/2502.13681 (v1 2025-02-19; quoted v2 2025-03-06)
2. https://arxiv.org/abs/2412.10133 (v1 2024-12-13; v2 2025-04-30)
3. https://arxiv.org/abs/2507.09063 (2025-07-11)
4. https://arxiv.org/abs/2503.14443 (2025-03-18)
5. https://arxiv.org/abs/2412.06294 (2024-12-09)
6. https://arxiv.org/abs/2505.04254 (2025-05-07)
7. https://arxiv.org/html/2504.21798v1 (2025-04-30)
8. https://arxiv.org/abs/2505.23419 (v1 2025-05-29; v2 2025-06-01)
9. https://arxiv.org/abs/2603.05026 (v1 2026-03-05; quoted v3 2026-10-03)
10. https://arxiv.org/abs/2512.06915 (v1 2025-12-07; v3 2025-12-12)
11. https://arxiv.org/abs/2601.16489 (2026-01-23)
12. https://arxiv.org/abs/2606.05238 (v1 2026-06-03; v2 2026-08-30)
13. https://arxiv.org/abs/2603.06739 (v1 2026-03-06; v2 2026-03-11)
14. https://code.claude.com/docs/en/memory (undated)
15. https://code.claude.com/docs/en/best-practices (undated)
16. https://learn.chatgpt.com/docs/environments/cloud-environment (undated; redirect from developers.openai.com/codex/cloud/environments)
17. https://agents.md (undated)
18. https://factory.com/news/agent-readiness (2026-01-20)
19. https://docs.factory.com/agent-readiness/overview (undated)
20. https://docs.devin.ai/onboard-devin/repo-setup (undated)
21. https://docs.devin.ai/onboard-devin/knowledge-onboarding (undated)
22. https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/customize-the-agent-environment (undated)
23. https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions (undated)
24. https://jules.google/docs/environment/ (undated)
25. https://cursor.com/docs/context/rules (undated)
26. https://arxiv.org/abs/2602.11988 (v1 2026-02-12; quoted HTML v3 2026-09-29)
27. https://arxiv.org/abs/2601.20404 (v1 2026-01-28; v2 2026-03-30)
28. https://arxiv.org/abs/2511.12884 (v1 2025-11-17; v2 2026-08-09)
29. https://arxiv.org/abs/2607.27250 (2026-07-28, REALM 2026)
30. https://arxiv.org/abs/2605.10039 (2026-05-11)
31. https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals (2026-01-27)
32. https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/ (2025-11-19)
33. https://cursor.com/blog/bugbot-learning (2026-04-08)
34. https://docs.coderabbit.ai/knowledge-base/learnings (undated)
35. https://greptile.com/docs/how-greptile-works/memory-and-learning (undated)
36. https://graphite.com/docs/ai-reviews (undated)
37. https://infoq.com/news/2026/01/claude-code-creator-workflow (2026-01-10, secondary)
38. https://arxiv.org/abs/2607.13091 (2026-07-13)
39. https://arxiv.org/abs/2607.03316 (v1 2026-07-03; v2 2026-07-23)

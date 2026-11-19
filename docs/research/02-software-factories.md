# Agentic software factories: practice, evidence, design rules

Research date: 2026-11-16. Target: Issue -> orchestrator (Claude Code) -> research/builder/reviewer subagents -> gates (lint, typecheck, unit, integration, e2e, security) -> PR + human approval, for one small team.

Conventions: [Sn] points to the source list (URL, date). Quotes are as returned by page fetches on 2026-11-16 (spot-check before external use); unquoted figures are paraphrased from the cited fetch. UNVERIFIED means no fetched primary quote was found. Evidence grades: **A** controlled study; **B** independent survey, academic study or large-sample telemetry; **C** vendor self-report about its own system; **D** convergent practice across 3+ independent orgs.

## 1. "Claude writes ~90% of its own code"

| Date | Who | Statement | Scope / metric |
|---|---|---|---|
| 2025-03-10 | Dario Amodei, CFR [S1] | "I think we'll be there in three to six months—where AI is writing 90 percent of the code." | Industry-wide prediction. Same answer: "the programmer still needs to specify ... what are the conditions of what you're doing" |
| 2025-09-23 | Boris Cherny via Pragmatic Engineer [S2] | "around 90% of Claude Code is written with Claude Code." | Claude Code repo |
| 2025-10-15 | Amodei, Dreamforce [S3] | "within Anthropic and within a number of companies that we work with, that is absolutely true now." | Transcript per [S4]: "on on many teams you know not uniformly" |
| 2025-10-22 | Ryan Greenblatt, Redwood [S4] | "much less than 90%, more like 50%." | External estimate, merged lines, all of Anthropic |
| 2025-12-27 | Cherny on X [S6] | "Every single line was written by Claude Code + Opus 4.5." | His own 259 PRs in 30 days |
| 2026-01-29 | Cherny via Fortune [S8] | "For me personally, it has been 100% for two+ months now, I don't even make small edits by hand" | Personal. Fortune paraphrases a spokesperson: 70-90% company-wide, ~90% Claude Code (verbatim UNVERIFIED) |
| 2026-03-07 | Cherny on X [S9] | "Can confirm Claude Code is 100% written by Claude Code" | Claude Code repo |
| 2026-06 | Anthropic Institute [S10] | "As of May 2026, more than 80% of the code we merge into Anthropic's codebase was authored by Claude." | **Only measured figure found:** "the share of lines merged to production that can be attributed to Claude". Pre-Feb 2025: "low single digits". Leadership's "90% or more" is "including scripts and experimental code" |
| 2026-10-15 | Claude Code team [S11] | "We've said before that Claude writes about 90 percent of Claude Code's own code." | Claude Code repo |

**What it means.** Line-attribution shares of human-directed, human-reviewed work, not unattended self-optimization:
- "much of the code is written by Claude, with the engineer directing and reviewing"; "humans supply the goal, but they no longer need to supply the method" [S10]. "A person is accountable for every change that ships, whoever typed it"; agent approvals "never count as a person's" [S11].
- "We are not there yet, and recursive self-improvement is not inevitable" [S10].
- Lines are not productivity: 8x merged lines per engineer "is almost certainly an overstatement of the true productivity gain"; staff self-estimate 4x, "the true degree of uplift in March was somewhat lower" [S10]. Quality "somewhat worse than human-written code ... in late 2025, is roughly at parity today" [S10].
- Delegation is partial: over half of 132 surveyed staff could "fully delegate" only 0-20% of their work (Aug 2025) [S5].

**Claude Code team workflow** (Cherny thread 2026-01-02 [S7]; [S11]):
- "I run 5 Claudes in parallel in my terminal" (plus 5-10 web sessions [S7]).
- Plan mode first: "A good plan is really important!" [S7].
- Mistake ledger: "Anytime we see Claude do something incorrectly we add it to the CLAUDE.md, so Claude knows not to do it next time." Done during review by tagging Claude on a coworker's PR; he calls it the team's version of "Compounding Engineering" [S7].
- Verification loop "will 2-3x the quality of the final result" (his estimate, unmeasured); subagents "code-simplifier" and "verify-app" [S7].
- By Oct 2026: repeated review flags fixed "in the skill, with a lint rule, or with updates to instructional files"; "Any incidents are now an eval", run daily against the reviewer [S11].

## 2. Factory designs

**Claude Code team review (Anthropic, 2026-10-15) [S11].** (1) Pre-PR: "Claude runs the tests, build and linter; a second agent reviews the diff in a fresh context"; told to "show the output instead of saying it's done". (2) CI: "Lint, types, tests across platforms, build and packaging. Red blocks the merge." (3) AI review: "Agents hunt for bugs in parallel, verifiers vote on each finding". (4) Separate security pass; open findings block. (5) Risk tiers: low "None required once automated review and security checks are green", medium "One person", high "Two people"; "The change sets the tier, not the author." (6-7) Merge queue, flags, staged release, rollback. Outcome (C): merged PRs "more than doubled while the share that had to be reverted fell by more than 40 percent" (Jun-Sep). Failure: a PR ran "more than fifty rounds of review and fixes overnight"; fix: "After three rounds, the reviewer asks the author to step back". Gap: "We don't yet have circuit breakers". Product version (2026-03-09) [S12]: PRs with substantive comments 16% -> 54%; "less than 1% of findings are marked incorrect"; "It won't approve PRs — that's still a human call."

**Anthropic long-running harness (2025-11-26) [S14].** Initializer agent sets up environment, feature-list JSON (only `passes` editable), `claude-progress.txt`, git; coding agents work "only one feature at a time". Failures: "Claude declares victory on the entire project too early"; marks features complete "without proper testing". Rule: "It is unacceptable to remove or edit tests". **Follow-up (2026-03-24) [S15]:** planner/generator/evaluator; agents "reliably skew positive when grading their own work"; a "sprint contract" defines done before coding; evaluator drives Playwright. Solo 20 min/$9 vs harness 6 h/$200, quality gap "immediately apparent". "every component in a harness encodes an assumption about what the model can't do on its own."

**Anthropic C compiler (2026-02-05) [S17].** 16 agents, ~2,000 sessions, ~$20k, 100k lines. "I don't use an orchestration agent" (lock files in git). "it's important that the task verifier is nearly perfect, otherwise Claude will solve the wrong problem." Late regressions forced a CI gate. "The test harness should not print thousands of useless bytes."

**Anthropic multi-agent research (2025-06-13) [S16].** Orchestrator-worker, +90.2% on internal eval, "about 15× more tokens than chats"; "most coding tasks involve fewer truly parallelizable tasks than research."

**StrongDM Software Factory (2026-02-06) [S19].** "Code must not be written by humans"; "Code must not be reviewed by humans." Scenarios are end-to-end user stories "often stored outside the codebase" (holdout) because "A test, stored in the codebase, can be lazily rewritten to match the code" and "Tests can be reward hacked". Gate is probabilistic "satisfaction": "what fraction of them likely satisfy the user?" Digital Twin Universe: "behavioral clones of the third-party services" (Okta, Jira, Slack, Google apps), "thousands of scenarios per hour". Spend bar: "$1,000 on tokens today per human engineer". No outcome metrics published. Three-person team since July 2025; Willison questions the cost and the no-review stance [S20]. Small-team fit: holdout scenarios yes; twin universe and spend no.

**OpenAI Harness engineering (2026-02-11) [S21, primary returned 403].** Via Böckeler [S22]: "no manually typed code at all", >1M lines in 5 months; harness = context engineering, architectural constraints (custom linters, structural tests), "garbage collection" agents that periodically find doc inconsistencies and constraint violations; "When the agent struggles, we treat it as a signal: identify what is missing." Critique: "What I am missing in the write-up is verification of functionality and behaviour." Via InfoQ [S23]: docs "serve as the single source of truth for agents"; agents read "logs, metrics, and spans"; "mechanically enforced with linters and CI validation". UNVERIFIED (search-index paraphrase only): ~100-line AGENTS.md as a map into `docs/`; agent-to-agent review with optional human review; agents merging own PRs. OpenAI's guide [S24, undated]: "Engineers delegate the initial code review to an agent, but own the final review and merge process."

**Stripe Minions (2026-02-09/19) [S25, S26].** "fully unattended and built to one-shot tasks"; launched from Slack or tickets; isolated devboxes. Blueprints: "a given node can run either deterministic code or an agent loop". ~500 MCP tools, "an intentionally small subset of tools by default". Local lint "in well under a second", then CI with autofix; "Why have only one or two rounds of CI?", then human. Outcome (C): "Over 1,300 Stripe pull requests" weekly, "human-reviewed, but containing no human-written code."

**Cursor (2026-01-14, 2026-02-05) [S27, S28].** Flat coordination failed: "With no hierarchy, agents became risk-averse." Planners/workers/judge; browser run "close to a week, writing over 1 million lines of code across 1,000 files". "The harness and models matter, but the prompts matter more." Redesign: judge removed, integrator "an obvious bottleneck", small error rate tolerated.

**Spotify Honk (2025-12-09; 2026-03-18) [S29, S30].** Worst failure: "a PR that passes CI but is functionally incorrect." Verifiers auto-activate (Maven "activates if it finds a pom.xml"), enforced by a Claude Code stop hook. LLM judge on "the diff of the proposed change and the original prompt" vetoed "about a quarter"; agent recovers "half the time"; main trigger scope creep. Sandbox: "limited permissions, few binaries, and virtually no access to surrounding systems." 2026: judge dropped as "too rigid, blocking valid changes"; "1,000 merged pull requests every 10 days"; "PR review, not code generation, the new bottleneck."

**Ramp Inspect [S31, post undated; InfoQ 2026-01-23].** "~30% of all pull requests merged to our frontend and backend repos are written by Inspect." "closes the loop on verifying its work" via tests, telemetry, flags; frontend "visually verifies its work". "You do not want to knowingly create a vector for unreviewed code." Later ~75%: UNVERIFIED.

**Factory.ai (2026-01-20) [S32].** Agent Readiness: 8 pillars, 5 levels (linters, type checkers, pre-commit hooks, local tests, AGENTS.md). "The agent is not broken. The environment is." No productivity outcomes.

**GitHub Copilot coding agent [S33, undated docs].** Pushes only to `copilot/` branches; "cannot approve or merge a pull request"; requester cannot approve; "workflows are not triggered until Copilot cloud agent's code is reviewed".

**Every (2025-12-11) [S34].** Plan, work, review, compound; "expect each feature to make the next feature easier to build"; ~80% of effort in plan and review; 12 parallel review subagents; five products each run primarily by one person (C).

## 3. Outcomes and limits

- **Perception vs measurement (A).** METR RCT (16 devs, 246 tasks): developers "take 19% longer" while expecting +24% and believing +20% afterwards [S35]. 2026 rerun: "-18% with a confidence interval between -38% and +9%" but "an unreliable signal" since 30-50% withheld tasks; treated as "a lower-bound" [S36]. Survey: "median 1.4–2x change in the value"; "survey results are not necessarily grounded in reality" [S37].
- **Throughput up, stability down (B).** DORA (~5,000): "AI doesn't fix a team; it amplifies what's already there"; "AI adoption does continue to have a negative relationship with software delivery stability"; 30% "little or no trust" [S38].
- **Review bottleneck (B, vendor telemetry).** Faros 2025 (10k devs): "PR review time increases 91%", PR size +154%, "no significant correlation between AI adoption and improvements at the company level" [S39]. Faros 2026 (22k): throughput +33.7%, "Median time in review is up 441.5%", "incidents-to-PR ratio is up 242.7%", churn +861%, "Pull requests merged without any review, human or agentic, are up 31.3%" [S40]. Anthropic: if humans "can't review code as quickly as Claude can generate it, human review will become the bottleneck" [S10].
- **Quality and security (B).** GitClear (211M lines): duplicated blocks up "8 times during 2024", moved lines down "39.9 percent" [S41]. Veracode: vulnerabilities in "45 percent of all test cases"; models "are not improving at security" [S42]. CodeRabbit "1.7x more issues": UNVERIFIED.
- **Agent PRs in the wild (B).** 9,799 human-reviewed agentic PRs: ~63% merged (computed from counts); "only 35.7% of rejected PRs reflected clear agentic failures" [S43].
- **Multi-agent failure (B).** MAST: 14 modes in 3 categories (system design, inter-agent misalignment, task verification), "1600+ annotated traces collected across 7 popular MAS frameworks"; "sole reliance on final-stage, low-level checks is inadequate"; "the presence of a verifier is not a silver bullet"; best fixes +9.4% to +15.6% [S44].
- **Context loss (D).** Cognition: "Share context, and share full agent traces, not just individual messages"; "Actions carry implicit decisions, and conflicting decisions carry bad results" [S45]. 2026: "multi-agent systems work best today when writes stay single-threaded"; a clean-context reviewer "catches an average of 2 bugs per PR"; parallel writers still fail [S46].
- **LLM judges age.** Spotify [S30] and Cursor [S28] removed theirs; Anthropic's evaluator still missed subtle bugs, "clearly more verification headroom" [S15].

## 4. Synthesis

| Stage | Best implementations do | Metric (sourced, or *proposed*) |
|---|---|---|
| Issue | Turn issue into spec with acceptance criteria before code: sprint contract [S15], plan step [S34]; launch from where work lives [S25] | *Issues with explicit criteria; clarification requests* |
| Orchestrator | Deterministic workflow with agent nodes [S26]; start simple, delete parts as models improve [S15][S28] | *Cost, wall time, rounds per issue* |
| Research | Read-only, parallel allowed, since "writes stay single-threaded" [S46]; coding is less parallelizable than research [S16] | *Tokens* |
| Builder | One writer per issue, own worktree/sandbox, small toolset [S26][S29]; one feature at a time [S14]; cannot edit acceptance tests [S14][S19] | *First-pass CI green*; PR size [S39] |
| Reviewer | Fresh context, read-only, diff + spec only [S18][S46]; findings verified and ranked [S12]; told to skip style ("A reviewer that's asked to find problems will always find *something*" [S18]); cap 3 rounds [S11] | Finding precision via author responses [S11]; veto rate [S29] |
| Lint/format | Pre-push and hook, sub-second [S26][S7] | *Lint failures reaching CI* |
| Typecheck, unit | Required CI, "Red blocks the merge"; agent runs first and shows output [S11][S29] | CI rounds (cap 1-2 [S26]) |
| Integration | Fakes or twins for external services [S19] | *Flake rate* |
| E2E | Browser automation "as a human user would" [S14][S15]; holdout scenarios builder never sees [S19] | Satisfaction share [S19] |
| Security | Separate blocking pass [S11]; needed per [S42] | *Open findings at merge* |
| PR + approval | Risk tiers; agent approval never counts; requester cannot self-approve; agent cannot run changed CI unreviewed [S11][S33] | Time to first review, revert rate, incidents per PR [S11][S40] |
| Compound | Repeat finding -> lint rule, hook, test or CLAUDE.md line; incident -> eval [S7][S11][S22]; "If you keep adding emphasis to a `CLAUDE.md` line and Claude still misses it, that's a sign the line belongs in a hook" [S18] | Author responses to findings [S11]; *repeat-finding rate* |

**Design rules (strongest evidence first)**

1. **Measure outcomes, not output.** Track reverts, escaped incidents, time in review; distrust self-reported speedups and line shares ("don't confuse throughput with success" [S13]). A [S35] (perception gap; [S36] is context only), B [S39][S40], C [S10].
2. **Gates are deterministic and block; the agent must show evidence.** "Done" = commands passed with output attached, not the agent's claim. B indirect [S44], D [S11][S14][S17][S26][S29].
3. **Security is its own blocking gate.** B [S42], C [S11].
4. **Single writer per change; parallelize only reads, review and independent issues.** B indirect [S44], D [S16][S27][S45][S46].
5. **Reviewer is separate, fresh-context and read-only.** Self-grading skews positive. C [S11][S15][S18][S46] (two orgs; Spotify's diff-plus-prompt judge [S29] is partial support).
6. **Acceptance tests are protected or held out from the builder.** D [S14][S19][S17][S24].
7. **Cap loops, then escalate to a human.** 1-2 CI rounds, 3 review rounds. C [S11][S26].
8. **Human approval scales with risk and is never self-granted.** Under high AI adoption, unreviewed merges rose 31.3% and incidents per PR 242.7% (no causal link shown). B [S40], D [S11][S31][S33].
9. **Design for review as the bottleneck:** one concern per PR, small diffs, evidence in description. B [S38][S39][S40], C [S30].
10. **Compound every mistake into the harness,** pruning CLAUDE.md and promoting ignored lines to hooks. D [S7][S11][S22][S34]; no controlled evidence.

**Does not transfer to one small team:** StrongDM's spend and no-review rule [S19][S20], Cursor-scale swarms [S27][S28], Stripe's ~500-tool platform [S26]. LLM-as-judge gates: optional, evaluate before trusting, expect removal [S28][S30].

## Sources

- S1 2025-03-10 https://www.cfr.org/event/ceo-speaker-series-dario-amodei-anthropic
- S2 2025-09-23 https://newsletter.pragmaticengineer.com/p/how-claude-code-is-built
- S3 2025-10-16 (BI via AOL) https://www.aol.com/articles/anthropic-ceo-says-90-code-030401205.html
- S4 2025-10-22 https://blog.redwoodresearch.org/p/is-90-of-code-at-anthropic-being
- S5 2025-12-02 https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic
- S6 2025-12-27 https://x.com/bcherny/status/2004887829252317325 (fetched via https://api.fxtwitter.com/bcherny/status/2004887829252317325)
- S7 2026-01-02 https://x.com/bcherny/status/2007179832300581177 (fetched via https://threadreaderapp.com/thread/2007179832300581177.html); InfoQ 2026-01-10 https://www.infoq.com/news/2026/01/claude-code-creator-workflow
- S8 2026-01-29 https://fortune.com/2026/01/29/100-percent-of-code-at-anthropic-and-openai-is-now-ai-written-boris-cherny-roon/
- S9 2026-03-07 https://x.com/bcherny/status/2030109840555790357
- S10 June 2026 (page undated, "Update 9/18/2026"; press dates it 2026-06-04/05) https://www.anthropic.com/institute/recursive-self-improvement
- S11 2026-10-15 https://claude.dev/blog/solving-code-review-at-anthropic/ (claude.dev reported as Anthropic's developer hub; not confirmed on an Anthropic-hosted page)
- S12 2026-03-09 https://claude.com/blog/code-review
- S13 2026-06-03 https://claude.com/blog/running-an-ai-native-engineering-org
- S14 2025-11-26 https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- S15 2026-03-24 https://www.anthropic.com/engineering/harness-design-long-running-apps
- S16 2025-06-13 https://www.anthropic.com/engineering/multi-agent-research-system
- S17 2026-02-05 https://www.anthropic.com/engineering/building-c-compiler
- S18 undated docs https://code.claude.com/docs/en/best-practices
- S19 2026-02-06 https://factory.strongdm.ai/
- S20 2026-02-07 https://simonwillison.net/2026/Feb/7/software-factory/
- S21 2026-02-11 https://openai.com/index/harness-engineering/ (403)
- S22 2026-02-17 https://www.martinfowler.com/articles/exploring-gen-ai/harness-engineering-memo.html
- S23 2026-02-21 https://www.infoq.com/news/2026/02/openai-harness-engineering-codex/
- S24 undated https://learn.chatgpt.com/guides/build-ai-native-engineering-team
- S25 2026-02-09 https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
- S26 2026-02-19 https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2
- S27 2026-01-14 https://cursor.com/blog/scaling-agents
- S28 2026-02-05 https://cursor.com/blog/self-driving-codebases
- S29 2025-12-09 https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
- S30 2026-03-18 https://www.infoq.com/news/2026/03/spotify-honk-rewrite/
- S31 undated https://builders.ramp.com/post/why-we-built-our-background-agent ; 2026-01-23 https://www.infoq.com/news/2026/01/ramp-coding-agent-platform/
- S32 2026-01-20 https://factory.com/news/agent-readiness
- S33 undated https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/risks-and-mitigations
- S34 2025-12-11 https://every.to/chain-of-thought/compound-engineering-how-every-codes-with-agents
- S35 2025-07-10 https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- S36 2026-02-24 https://metr.org/blog/2026-02-24-uplift-update/
- S37 2026-05-11 https://metr.org/blog/2026-05-11-ai-usage-survey/
- S38 2025-09-23 https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report
- S39 2025-07-23 https://www.faros.ai/blog/ai-productivity-paradox-report-2025
- S40 2026-04-12 https://www.faros.ai/blog/ai-acceleration-whiplash-takeaways
- S41 2025-02-20 https://www.devclass.com/ai-ml/2025/02/20/ai-is-eroding-code-quality-states-new-in-depth-report/1626250
- S42 2025-07-30 https://www.veracode.com/press-release/ai-generated-code-poses-major-security-risks-in-nearly-half-of-all-development-tasks-veracode-research-reveals/
- S43 2026-05-21 https://arxiv.org/abs/2605.22534
- S44 2025-03-17 (v3 2025-10-26) https://arxiv.org/abs/2503.13657
- S45 2025-06-12 https://cognition.com/blog/dont-build-multi-agents
- S46 2026-04-22 https://cognition.com/blog/multi-agents-working

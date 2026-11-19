# Feature workflow evidence

## Design choices

- Start with one observable outcome and a proof that goes through the normal entry point. Use the
  repository's terminology and interfaces to answer questions before asking the owner. Split only
  when a part delivers a separately verifiable outcome. Pocock's current workflow links tracer-bullet
  tickets through dependencies. Osmani separates verification checkpoints from the implementation
  steps between them. [Pocock's skills](https://github.com/mattpocock/skills),
  [Osmani's skills](https://github.com/addyosmani/agent-skills).
- Treat tests and production-like scenarios as the primary evidence. StrongDM uses external holdout
  scenarios and feedback loops. OpenAI keeps small plans short and writes durable plans for complex
  work. Anthropic found that removing sprint decomposition worked with a stronger model while
  independent evaluation still helped where capabilities fell short. These are different settings
  from this factory and do not establish the same effect here. [StrongDM's factory](https://factory.strongdm.ai/principles),
  [OpenAI's harness](https://openai.com/index/harness-engineering/),
  [Anthropic's harness](https://www.anthropic.com/research/harness-design-long-running-apps).
- Keep EGM's independent review and side-effect discovery for consequential plans. A focused pass
  traces a real path and checks failures at the boundaries it crosses. It can bring the remaining
  product decisions to the owner in one batch. The full EGM workflow, with a multi-turn interview,
  seven fresh perspectives and design review, is a stronger intervention worth evaluating where
  one pass misses important issues. [EGM walkthrough](https://github.com/google/elephant-goldfish-model/blob/main/docs/getting_started.md).
- Keep CodeGraph selective. Use it to find relevant callers in an existing index. A controlled
  study found that structured retrieval sometimes cost more overall, even when individual retrievals
  improved. Keep Plannotator available for deliberate human annotation of a contested contract or
  a delivery diff. These are optional tools around the same factory commands. [Cost study](https://arxiv.org/abs/2609.30725),
  [CodeGraph](https://github.com/colbymchenry/codegraph), [Plannotator](https://github.com/backnotprop/plannotator).

## Terra trials

Fresh GPT-6.1 Terra sessions read one of two disposable projects and produced implementation
handoffs. One request changed a label. The other added overdue-invoice email across a scheduler,
outbox, mail worker, and support view. The repo answered eligibility and enqueue deduplication.
The rollout policy and meaning of a support event were deliberately unresolved.

| Prompt | Label output / time | Reminder output / time | Reminder findings |
|---|---:|---:|---|
| Plain | 379 tokens / 19.6 s | 510 tokens / 20.2 s | Found both explicit owner decisions |
| Focused | 300 tokens / 13.6 s | 760 tokens / 41.5 s | Same decisions and clearer proof, missed changes after enqueue |
| Seven lenses in one prompt | 837 tokens / 24.3 s | 1,326 tokens / 36.1 s | Found the delivery gap and raised several additional questions |
| Focused with an explicit delivery trace | — | 907 tokens / 25.6 s | Found the delivery gap and distinguished enqueue deduplication from receipt |

Read-only cold reviews took 5.6–8.7 seconds and emitted 5–79 tokens. The label passed. A reviewer
of the focused handoff caught a race between selection and enqueue. A reviewer of the revised
handoff found that its acceptance still implied exactly-once receipt while the available outbox
only proved deduplicated enqueue. This supports a risk-based independent review. It does not
show a general token or speed advantage over EGM. The broad prompt was a proxy, with no interview
or agent swarm. Each cell is one trial, and wall times are sensitive to scheduling and cache.

One separate live Terra run implemented and reviewed a small calculator ticket in a disposable
two-repo project. The engine delivered after one build round, a real unittest gate, and review.
The harness recorded results and committed the builder's output, so this exercised the engine
and the manual result path. A first run correctly parked when the live plugin changed during review.

A second Terra run delivered an addition and a subtraction ticket on separate branches. The
subtraction branch used the exact reviewed addition commit and its own diff contained one commit.
Reopening the addition parked the delivered subtraction branch for human review. The subtraction
review passed a mock assertion that checked which helper was called. The behavior tests already
covered the operation, so prompt guidance now asks builders and reviewers to verify required reuse
in the diff and reserve mock interaction assertions for observable contracts.

## Paired implementation trial

Both arms used GPT-6.1 Terra with the same starting code and decided requirements. The synthetic
Python/SQLite feature had three existing entry points for scheduling overdue invoice reminders,
delivering them, and showing support history. The direct arm built and checked its own change in
one session. The staged arm used a short handoff, a builder, and a cold code review, followed by
one fix and a fresh review. The models worked through disposable repos using the trial harness.

| Arm | Sessions | Time | Input tokens | Cached input | Output | Independent checks |
|---|---:|---:|---:|---:|---:|---:|
| Direct | 1 | 52.1 s | 100,926 | 85,376 | 2,303 | 6 of 6 |
| Short plan and review | 5 | 150.6 s | 513,967 | 451,584 | 5,660 | 6 of 6 after one fix |

The first staged build passed its own suite. The cold reviewer found that an invoice paid after
selection could still be queued. The independent suite reproduced that failure on the reconstructed
first build and passed after the fix. Its other cases covered concurrent scheduling, rollout and due
dates, reopening the database, current billing details, cancellation, and a provider that accepts
a send before reporting an error. The read-only reviewer had no writable temporary directory for
the full suite. An independent local runner executed the tests for all versions.

This pair supports reusing a settled contract and spending review effort on concrete state transitions.
The direct arm passed with less time and fewer tokens in this fixture. Fresh review recovered a defect
in the staged arm. The trial does not establish how often either outcome occurs on real projects or
how full EGM would compare. Token counts include tool context. Cached input is reported separately.

## Five-phase EGM review trial

Fresh GPT-6.1 Terra sessions reviewed the same synthetic regional stock-ledger migration. The
focused arm used one independent factory-style review. The EGM arm used the installed EGM 0.1.1
role instructions and rubrics for its five review phases, with parallel calls within a phase
and earlier findings passed to the second zoom-out. Both arms read the design and tickets. The
fixture had no accompanying implementation. The harness ran the review sessions and scored
the findings manually. It omitted the interactive authoring workflow and final EGM synthesis.

| Arm | Sessions | Time | Input tokens | Cached input | Output tokens | Seeded defects found |
|---|---:|---:|---:|---:|---:|---:|
| Focused review | 1 | 18.2 s | 23,535 | 12,032 | 659 | 6 of 6 |
| EGM review phases | 10 | 103.4 s | 244,864 | 150,656 | 6,718 | 6 of 6 |

Both found overlapping writers that can over-reserve stock, checkpoints that skip events,
stale backfill overwrites, events rejected by old consumers, courier retries that outlive
deduplication, and rollback that loses acknowledged writes and shipment confirmations. The
first EGM zoom-out already found all six. Additional EGM findings included warehouse transfers
spanning partitions, the identity of retry results across ledgers, and availability requirements
for a stalled handoff. Its implementation reviewers also asked for exact file-level changes,
which could not be checked against a codebase in this fixture.

Keep one focused pass as the factory default and trace requests during and after a cutover. A
second design-focused pass is worth considering when cross-system invariants, failure recovery
or rollout sequencing remain unclear. The complete phase sequence took about 5.7 times the wall
time and emitted 10.2 times the output tokens in this fixture. The result measures one seeded
document review. Real implementation quality and the cost of EGM authoring remain open.

## Tests, architecture, and learning

Caldo's pruning rubric distinguishes proof of behavior from assertions against a fake or an
implementation detail. Keep a negative guarantee when callers still rely on it and keep distinct
failure coverage at different boundaries. The factory applies these checks to the current diff.
The structural review asks which code must change together and checks for hidden coupling or
unnecessary indirection. A broader cleanup starts as a scoped evaluation and a ticket with a
behavior-preserving proof. [Prune tests](https://github.com/caldoai/skills/blob/main/skills/prune-tests/SKILL.md),
[Untangle codebase](https://github.com/caldoai/skills/blob/main/skills/untangle-codebase/SKILL.md).

Two fresh Terra reviewers classified nine seeded cases against the old and revised rubrics.
Both kept meaningful retry, pricing and disclosure checks, flagged the same three weak tests,
and agreed about duplicate status policy, an unnecessary wrapper and useful encapsulation.
This small trial found no incremental classification gain. Use the concise rules inside ordinary
build and review, and reserve a wider audit for an explicit scope.

Factory learning has two inputs. Repeatable agent failures or owner corrections can yield a small,
versioned instruction change. A new observation about the factory itself can become a replayable
evaluation and then a normal ticket. Hermes similarly persists workflow lessons and can stage
changes for review. Measure a learning change on the case that exposed the issue and at least one
nearby case before claiming it improved quality or speed. [Hermes learning](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory),
[Anthropic's evaluation guide](https://www.anthropic.com/research/demystifying-evals-for-ai-agents).

In an isolated learning trial, Terra proposed a one-file rule change for a synthetic test runner.
The factory accepted the versioned change. Fresh roles replayed exits 5, 1 and 0. Before the
change the result was `FAIL FAIL PASS`. After it, the result was `NO_TESTS FAIL PASS`. The harness
committed the proposed rule and recorded the learner result.

The self-hosting trial reproduced a real bug with run IDs for legacy effort directories containing
spaces. An evaluation became a normal build ticket in an isolated factory checkout. The focused
stop-hook test went from red to green and the factory gate passed 80 tests. The current agent
handled research, implementation and review locally because the automatic approval denied sending
the factory source to an external agent. The delivered patch was applied to the main working tree.

A disposable checkout reproduced a learner rollback that took back an unrelated operator commit.
A later regression test reproduced a related issue with uncommitted work being stashed. The new
learner works read-only and supplies a proposal. Rejected proposals leave the checkout untouched.
An accepted proposal is committed in a temporary worktree before it can reach the installation.
Tests cover intervening commits, branch switches, uncommitted work, failed replay and adoption.

The first paired replay covers code-review test quality. The harness recorded a proposed rule
through the Factory CLI in a disposable plugin checkout. Fresh Terra sessions returned PASS/PASS
with the weak instructions and CHANGES/PASS with the candidate. The first case was an unnecessary
assertion about a private helper. The other checked provider delivery after a lost response and
needed to be preserved. The calls took 5.7 and 7.5 seconds and emitted 27 and 28 tokens. Feeding
these results back through the CLI produced a clean adoption commit whose only change was the
reviewer role file. The proposal and cases were synthetic. The live trial exercised the replay and
adoption stages. Broader automatic adoption still needs held-out cases for other roles and skills.

## Review after implementation

The ordinary ticket gate and review cover the delivery at its recorded commits. A feature review
at implementation time can use that evidence to focus on shared outcomes and current code. The
evidence command reports reviewed commits present in the current checkout, deliveries from an older
contract, and tickets still open. Squash merges and unrecorded work need current proof.

A synthetic two-ticket pickup flow used the actual factory engine and test gates, with simulated
agent messages. The producer and worker were delivered separately. Both of their scoped tests
also passed after merging. One integrated check then passed a real producer event to the worker and
failed because the two tickets used different names for the ready status. The same check and both
scoped tests passed after aligning the consumer. This detected a cross-ticket failure with no extra
model call. The implemented review path uses one fresh reviewer when the focused checks still
leave an important gap.

In a second synthetic pickup fixture, the merged happy-path check had passed and the contract
also promised a single courier delivery after a lost acknowledgement. A fresh Terra reviewer
requested one check using a courier that accepts the first request and then raises a timeout.
The independent check observed two accepted deliveries. The worker generated a new request key
on each attempt. Using a stable key reduced the count to one. The review took 8.0 seconds and
emitted 82 tokens. These fixtures measure two specific failure modes.

A subsequent evaluation reproduced old gate evidence being used after a new commit. The first
gate passed while the required file existed. A commit then removed the file and the engine started a
review with the earlier result. A separate case showed a green result after the checkout moved while
a gate was still running. Gate reports now record the tested checkout. The CLI replay passed first,
refreshed the gate after the new commit, failed the new check and returned to the builder. The engine
parks runs that move during a gate. Older archived passes without tested commits require current proof.

A concurrent CLI replay found that two queue commands could each claim a ticket before either
published its active run. The engine now locks the project state directory during a transition.
With two CLI processes, one started a run and the other ticket stayed open. In the same fixture,
two gate callers launched one check and both retrieved its result after the run was archived.
The agents and gate commands execute outside the project lock.

An interrupted queue command could leave a claimed ticket without an active run. The engine now
stores the run and original ticket revision before changing the status. In two disposable CLI
trials, the process exited immediately before publishing the active pointer and immediately after
writing the claimed status. The next command used the same run ID in each trial. An intervening
ticket edit stopped the resumed claim and preserved the new contents. Status reports claimed
tickets left without a saved run by older interruptions.

## Codex pilot with real plan approval

A disposable Python CLI project started with one passing test. Factory verification kept just
the profile and its ignore file before the first ticket was written. The pending JSON receipt
ticket was absent from the queue until a human approved its Markdown in the local Plannotator
browser session. The review command returned approved and the board moved the ticket to Backlog.

The Codex skill's native subagent path then used three GPT-6.1 Terra roles for research, build,
and fresh review. The orchestrator recorded each role's actual result through the CLI. The
builder produced one local commit, its gate passed both tests, and the reviewer passed the tested
commit. The engine delivered in one round, archived the run, and produced the PR draft. The
pending ticket moved to Ready for code review. An independent CLI check covered four order IDs
through both the new JSON output and the original text output.

The pilot also reproduced an onboarding gap. Detection missed an inline GitHub Actions run
list item, so the verified gate command had to come from reading the workflow. This run verified
manual Codex result recording for a backend ticket. The Codex UI role still needs a proof path
for skill loading. Automatic learning still needs qualified replays for additional roles.

## Readiness checks in disposable projects

Reopening a copy of the exact approved pilot issue made it eligible to run. Adding a review
comment preserved that approval. Changing the accepted output field removed it from the queue
and an explicit run request stopped for plan approval. Adding a shared contract also made the
old plan ineligible.

A CI detection prototype found the actual pilot command in an inline GitHub Actions step. It
also preserved a named GitHub step and a Bitbucket script list, and ignored multiline YAML
markers and step metadata. Chromium exercised a synthetic control at 390 and 1280 pixels. The
existing screenshot archive function copied both captures with identical hashes.

An independent executable check scored the original pilot commit and the actual Terra build
on five order IDs. Only the Terra build passed both the existing text contract and the new JSON
contract. A variant with broken text output and a variant with no change both claimed success in
their reports. The executable check detected the regression and the lack of improvement.
These probes ran outside the production workflow. Automatic builder scoring and the full Codex
UI run remain part of the pending readiness issues.

### Researcher learning trial

A disposable Factory prototype ran the existing learning protocol with `READY` and
`NEEDS-INFO` as researcher outcomes. The learner proposed one change after a synthetic booking
incident. The replay cases used other scenarios, were committed before the run, and supplied the
same inputs to fresh Terra sessions with the original and proposed instructions.

The original instruction passed both cases in the first run. The engine kept it and skipped the
candidate call. In a separate run with a deliberately faulty defaulting rule, the baseline passed
two of three cases. The candidate asked for a decision on split-tender credit and preserved the
two `READY` decisions for settled work. The engine adopted only the proposed change to
`roles/researcher.md` in that checkout (`6cb9bed2104cb9db065126d0820450cd8b91cdd1`). Nine
existing learning tests also passed against the prototype. This proves the two adoption outcomes
on the fixtures. It does not measure how often the live Factory's researcher needs a lesson.

### Builder learning trial

A disposable Factory prototype submitted one learner proposal to two Terra builders. Both
started from the same commit in separate checkouts and implemented the same receipt ticket.
Both reported `DONE` with two green tests. The baseline added an environment setting and failed
the independent check for the required `--format=json` invocation. The candidate passed that
check and preserved the original text and missing-argument behavior. The engine promoted only
the builder rule in the disposable Factory checkout (`6c7e6dcb0414b88c76abf63c10f37520166c07f3`).

A separate run of the executable scorer still caught an incorrect flag when the checkout's own
tests were green. It refused a candidate that broke the original output and detected a baseline
commit change after scoring. The learning engine also detected an edit to the committed starting
fixture. These cases verify the prototype with a seeded fault. The role scopes in this trial
were instructions to the agents and the checks detected changed inputs.

A separate run of the current UI workflow reproduced a delivery with `ui-1: PASS` and no
record of what the tester rendered. Evaluation `a3641ecc241062b7` is linked to the pending Codex
UI issue. The user chose a short browser check for small changes and screenshots for acceptance
criteria that depend on a visual comparison.

The Codex UI prototype used the installed design skill in the emitted builder prompt. A changed
prompt and an unexpected UI edit both triggered a follow-up with the skill attached. Chromium
verified a button label without an image and captured the responsive card layout at 390 and 1280
pixels. The prototype delivered the small change with the written browser observation. It held
a bare pass and a visual pass missing its requested screenshots. With both screenshots present,
it delivered the visual change and archived copies identical to the browser captures.

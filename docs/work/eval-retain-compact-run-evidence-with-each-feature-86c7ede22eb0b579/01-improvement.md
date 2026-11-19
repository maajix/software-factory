# 01 - Retain compact run evidence with each feature

Type: task
Status: ready-for-review
Blocked by: -

## Outcome

After a terminal ticket run, the effort contains the PR text when available, proven agent results, gate summary, and branch history. Transient files may be removed after that evidence is durable. Status, learning signals, reopens, and stacked builds still find the retained evidence.

## Acceptance

- After a terminal ticket run, the effort contains the PR text when available, proven agent results, gate summary, and branch history. Transient files may be removed after that evidence is durable. Status, learning signals, reopens, and stacked builds still find the retained evidence.

## Proof

Replay a two-ticket stack through delivery and rejection. Verify that both ticket deliveries have durable evidence under their effort, the transient run files were cleaned up, and status, reopening, and the learner still read old and newly retained runs.

Baseline: The two Terra calculator deliveries retained 30 files and 37,152 bytes in .factory/runs. Twelve files were raw logs, prompts, or finished process locks.

## Observation

Delivered runs remain in the runtime directory with prompts, raw logs, and a finished process lock. The feature folder has no delivery record.

Evaluation: 86c7ede22eb0b579

## Verification

- Replaying both Terra deliveries through the CLI retained 18 files and 12,454 bytes in the effort
  archives. The original run retained 30 files and 37,152 bytes. The replay used the recorded
  agent responses and patches and ran both gates again.
- The second delivery still used the reviewed base commit and was parked when the base ticket was
  rejected. The first ticket reopened on its original branch.
- The self-hosted factory delivered this change after its gate recorded 87 passing tests. The suite
  includes archive write failure, retry after publication, legacy history, learning signals, and
  screenshot retention.

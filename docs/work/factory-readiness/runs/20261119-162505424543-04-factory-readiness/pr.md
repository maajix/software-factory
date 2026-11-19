FEAT: 04 - Score builder lessons with executable replays

## Problem
Builder lessons currently have no independent replay gate, so a proposal for `roles/builder.md` remains available for manual evaluation. Builder reports cannot establish whether a patch meets acceptance criteria or preserves existing behavior; executable checks must score the produced code.

## Change
Committed `7b86def` to reject missing or unreadable replay inputs and deleted checkouts. The independent checks now cover unsupported-operation errors.

The fixture source and task remain unchanged for the live replay.

## Merge order
- `.` is stacked on `feature/minor-researcher-replay` at `bcc77753d4fb2975bb6b907097c39478abecf22b`.

## Verified
- `python3 -m unittest discover -s tests` (.): exit 0, 111 passed, 0 failed
- review-2: PASS

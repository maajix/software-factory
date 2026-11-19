FEAT: 03 - Replay researcher behavior before adopting a lesson

## Problem
Learning currently scores only reviewer proposals, so a researcher instruction cannot be adopted through independent replay. The Factory needs to distinguish settled planning requirements from consequential gaps while preserving passing behavior and the existing reviewer replay.

## Change
The live replay resolved the missing evidence. The disposable trial adopted the candidate change to `roles/researcher.md` in commit `ea98c6d`.

## Verified
- `python3 -m unittest discover -s tests` (.): exit 0, 108 passed, 0 failed
- review-2: PASS

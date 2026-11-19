FEAT: 02 - Deliver UI tickets across agent runners

## Problem
UI builds recorded through the shared CLI cannot prove that the builder received the design skill because the current check relies on a Claude Code transcript. UI review also accepts a bare `PASS`, even though delivery needs a browser observation and, for visual acceptance criteria, archived screenshots.

## Change
Committed the five review corrections in `7272cf1`. UI reviews now require explicit browser, screen, and observation fields; visual tickets also require narrow and wide observations and distinct labelled screenshots. Same-named captures are preserved, and the Codex instructions describe the shared handoff.

Small UI changes can still deliver without screenshots.

## Verified
- `python3 -m unittest discover -s tests` (.): exit 0, 114 passed, 0 failed
- review-2: PASS

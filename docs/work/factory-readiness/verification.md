# Factory readiness verification

Plannotator approved the four issue plans against contract revision `b82671dc9739ef0c`.
The Factory delivered each issue in an isolated checkout after passing its gate and a fresh
review. The combined code at `3cc89203e78ec7d1b8d16a2643cb66e5eb3fbbc5` passed all 120 tests.

- [factory-readiness/01](runs/20261119-115000634581-01-factory-readiness/pr.md) reviewed `aa1e208bd0b2019c7f582f8602700208fd5d4d5f`. Its recorded gate passed.
- [factory-readiness/02](runs/20261119-115028747575-02-factory-readiness/pr.md) reviewed `7272cf1c608e6542c1b0a95cecd847dabca5e0f9`. Its recorded gate passed.
- [factory-readiness/03](runs/20261119-115028838490-03-factory-readiness/pr.md) reviewed `bcc77753d4fb2975bb6b907097c39478abecf22b`. Its recorded gate passed.
- [factory-readiness/04](runs/20261119-162505424543-04-factory-readiness/pr.md) reviewed `7b86def1076199c8ca57b37d70493ca05e46e005`. Its recorded gate passed.

## Observed behavior

- `factory detect` found the Python unit command in a reconstruction of the approved pickup pilot.
  The regression suite covers mapping-style steps, Bitbucket script lists, and YAML block
  indicators and comments.
- Through `factory next` and `factory record`, Chromium verified the small label change with a
  browser observation and zero screenshots. At 390 and 1280 pixels, the visual case passed and
  archived both captures byte-for-byte. Unit tests also cover stale handoffs, browser evidence,
  and the existing Claude Code skill transcript path.
- Fresh Terra researcher sessions scored 1 of 2 and 2 of 2 on the independent notification
  cases. The disposable learning run adopted only `roles/researcher.md` at
  `ea98c6d03398267ca85591d53008b4b0a70eeb57`.
- The builder replay skipped a candidate when the baseline already passed. In the paired live
  trial the runner adopted only `roles/builder.md` at
  `e1969f45a792bac1f4153a495e5d5ae304be5527`. The corrected checker re-scored the same patches
  from 2 of 3 to 3 of 3. It rejected a regression of the error behavior, a missing check script,
  and a missing baseline checkout.

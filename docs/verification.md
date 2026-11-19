# Verification

The Software Factory 1.0.0 release snapshot passed all 120 unit tests. The Factory's four
self-hosted readiness changes went through Plannotator plan approval, project gates, and
fresh code review before acceptance.

| Area | Verified behavior |
| --- | --- |
| CI detection | Found an inline GitHub Actions run step in the pickup fixture. Regression tests cover mapping-style steps, Bitbucket script lists, and YAML block headers. |
| UI evidence | Chromium verified a small label change without screenshots. A responsive fixture archived both the 390 px and 1280 px captures. |
| Researcher learning | Fresh agents improved from one to two correct decisions on independent cases. The disposable checkout adopted only the researcher instruction. |
| Builder learning | Independent executable checks improved from two to three passes on the actual paired patches. The Factory rejected a regression, a missing check script, and a missing baseline checkout. |

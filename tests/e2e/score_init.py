#!/usr/bin/env python3
"""Score a /factory:init result on the the example project copy against the fixture expectations.

usage: score_init.py <the example project copy> [init-run.jsonl]
Checks what the profile must carry; facts that only appear in the init report are matched by keyword.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
prof = json.loads((root / ".factory/profile.json").read_text())
report = ""
if len(sys.argv) > 2:
    for line in open(sys.argv[2]):
        o = json.loads(line)
        if o.get("type") == "result":
            report = str(o.get("result", ""))
gates = {g["id"]: g for g in prof.get("gates", [])}
repos = {r["path"]: r for r in prof.get("repos", [])}
SUBS = ["example-backend", "example-frontend", "example-worker", "example-auth", "example-reporting"]


def gate(repo, cmd_rx, tier=None):
    for g in gates.values():
        if g["repo"] == repo and re.search(cmd_rx, g["cmd"]) and not g.get("disabled") and (tier is None or g.get("tier", "fast") == tier):
            return g
    return None


def base_ok(path):
    r = repos.get(path)
    return bool(r) and subprocess.run(["git", "-C", str(root / path), "rev-parse", "--verify", r["base"]],
                                      capture_output=True).returncode == 0


br = re.compile(prof.get("conventions", {}).get("branch_regex", "x^"))
cr = re.compile(prof.get("conventions", {}).get("commit_regex", "x^"))
status = prof.get("tracker", {}).get("status", {})
checks = [
    ("1 topology: parent + 5 submodules in repos", set(SUBS) | {"."} <= set(repos)),
    ("2 every repo base resolves", all(base_ok(p) for p in ["."] + SUBS)),
    ("3 Bitbucket named in the report", "bitbucket" in report.lower()),
    ("4 branch rule accepts the three prefixes", all(br.match(b) for b in ("bugfix/patch-x", "feature/minor-x", "feature/major-x-y"))),
    ("4 branch rule rejects other prefixes", not br.match("fix/x") and not br.match("feature/x")),
    ("5 commit rule accepts FEAT/FIX/UPT/DOCS", all(cr.match(c) for c in ("FEAT: a", "FIX: a", "UPT: a", "DOCS: a"))),
    ("5 commit rule rejects lowercase type", not cr.match("feat: a")),
    ("7 tracker markdown under docs/issues", prof.get("tracker", {}).get("root") == "docs/issues"),
    ("8 queue status includes open, claim word claimed", "open" in status.get("queue", ["open"]) and status.get("claimed", "claimed") == "claimed"),
    ("8 done statuses include resolved", "resolved" in status.get("done", ["resolved"])),
    ("11 backend fast gate pnpm test:ci", bool(gate("example-backend", r"test:ci", "fast"))),
    ("11 frontend fast gate pnpm test:ci", bool(gate("example-frontend", r"test:ci", "fast"))),
    ("11 reporting fast gate pnpm test", bool(gate("example-reporting", r"pnpm (run )?test\b", "fast"))),
    ("11 scanner fast gate pytest", bool(gate("example-worker", r"pytest", "fast"))),
    ("11 auth has no test gate", not any(g["repo"] == "example-auth" and "test" in g["cmd"] for g in gates.values())),
    ("12 backend slow gate test:system needs docker", bool((g := gate("example-backend", r"test:system", "slow")) and "docker" in g.get("requires", []))),
    ("12 backend tool tests gated with redis-server or uv", bool((g := gate("example-backend", r"test[:-]tools\b")) and set(g.get("requires", [])) & {"redis-server", "uv"})),
    ("12 drift checks deny-lists / wappalyzer present", bool(gate("example-backend", r"deny-lists:check")) and bool(gate("example-backend", r"wappalyzer-names:check"))),
    ("13 no format:check gate (CI does not run it)", not gate("example-backend", r"format:check")),
    ("tests expected on every test gate", all(g.get("expect_tests") for g in gates.values() if re.search(r"test(:ci|:system|:tools)?\b|pytest", g["cmd"]))),
    ("19 version file forbidden", any(".env.version" in p for p in prof.get("conventions", {}).get("forbidden_paths", []))),
    ("21 no existing agent config named in report", bool(re.search(r"no (existing )?(agent|\.claude|AGENTS)", report, re.I))),
    ("baselines recorded for enabled gates", all(g.get("baseline") for g in gates.values() if not g.get("disabled"))),
    (".factory/.gitignore covers runs/", "runs/" in (root / ".factory/.gitignore").read_text() if (root / ".factory/.gitignore").exists() else False),
]
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{sum(ok for _, ok in checks)}/{len(checks)} checks pass")
for g in gates.values():
    b = g.get("baseline") or {}
    print(f"  {g['id']:40} {g.get('tier', 'fast'):5} {b.get('status', '-'):8} {b.get('counts')} {b.get('seconds')}s {g.get('disabled') or b.get('reason') or ''}")

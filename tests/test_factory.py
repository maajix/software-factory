"""End-to-end tests of the engine with simulated agents, plus the pure parts. python3 -m unittest discover -s tests"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from factory import engine as E  # noqa: E402
from factory import detect as D  # noqa: E402
from factory import evaluate as V  # noqa: E402
from factory import gates as G  # noqa: E402
from factory import hooks as H  # noqa: E402
from factory import plans as A  # noqa: E402
from factory import profile as P  # noqa: E402
from factory import signals as S  # noqa: E402
from factory import stack as K  # noqa: E402
from factory import tracker as T  # noqa: E402
from factory.util import FactoryError, read_json, write_json  # noqa: E402


def sh(cwd, *cmd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    sh(path, "git", "init", "-q", "-b", "main")
    sh(path, "git", "config", "user.email", "t@example.com")
    sh(path, "git", "config", "user.name", "t")
    sh(path, "git", "config", "commit.gpgsign", "false")


TICKET = """# 0{n} - Thing {n}

Type: task
Status: open
Blocked by: {blocked}

## Question

Add thing {n}.
"""

BRIEF = """VERDICT: READY
BRANCH: feature/minor-thing
REPOS: svc
COMMIT_TYPE: FEAT

## Problem
Thing is missing.

## Plan
1. add thing.txt
"""

PASS = "VERDICT: PASS\n\n## Findings\n- [nit] naming: fine"
DONE = "VERDICT: DONE\n\n## Change\nAdded thing.txt."


class FlowBase(unittest.TestCase):
    """A parent repo with tickets, a service repo and a profile; helpers that simulate agents and gates."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        init_repo(self.root)
        (self.root / ".gitignore").write_text("svc/\n.factory/\n")
        issues = self.root / "docs/issues/eff/issues"
        issues.mkdir(parents=True)
        (issues / "01-thing.md").write_text(TICKET.format(n=1, blocked="-"))
        (issues / "02-other.md").write_text(TICKET.format(n=2, blocked="01, 03"))
        sh(self.root, "git", "add", ".")
        sh(self.root, "git", "commit", "-qm", "CHORE: init")
        svc = self.root / "svc"
        init_repo(svc)
        (svc / "a.txt").write_text("a\n")
        sh(svc, "git", "add", ".")
        sh(svc, "git", "commit", "-qm", "CHORE: init")
        write_json(self.root / ".factory/profile.json", {
            "repos": [{"path": ".", "base": "main"}, {"path": "svc", "base": "main"}],
            "gates": [{"id": "svc:test", "repo": "svc", "cmd": "test -f thing.txt && echo ' Tests  3 passed (3)'",
                       "tier": "fast", "expect_tests": True}],
            "tracker": {"type": "markdown", "root": "docs/issues"},
            "conventions": {"branch_regex": "^(bugfix/patch|feature/minor|feature/major)-[a-z0-9-]+$",
                            "commit_regex": "^(FEAT|FIX|UPT|DOCS|REFACTOR|TEST|CHORE): \\S"},
        })
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)

    def tearDown(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.tmp.cleanup()

    def stop_event(self, role, message, rid=None, stem=None, n=None, stop_active=False, skills=()):
        """A SubagentStop input whose transcript starts with the spawn header, as Claude Code writes it."""
        rid = rid or E.state(self.root)["active"]
        run = E.load_run(self.root, rid)
        stem = stem or run["pending"][f"factory:{role}"]
        n = n if n is not None else run.get("spawn_ids", {}).get(stem, 1)
        t = Path(self.tmp.name) / f"t-{rid}-{stem}-{n}.jsonl"
        t.write_text(json.dumps({"type": "user", "message": {
            "role": "user", "content": f"FACTORY RUN {rid} RESULT {stem} SPAWN {n}\nRead the prompt file."}}) + "\n" +
            "".join(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": f"s{i}", "name": "Skill", "input": {"skill": s}}]}}) + "\n"
                for i, s in enumerate(skills)))
        ev = {"agent_type": f"factory:{role}", "cwd": str(self.root), "last_assistant_message": message,
              "hook_event_name": "SubagentStop", "agent_transcript_path": str(t)}
        if stop_active:
            ev["stop_hook_active"] = True
        return ev

    def agent_returns(self, role, message, **kw):
        self.assertIsNone(H.subagent_stop(self.stop_event(role, message, **kw)))

    def next(self):
        return E.next_action(self.root)

    def active(self):
        return E.load_run(self.root, E.state(self.root)["active"])

    def run_gate(self):
        run = self.active()
        E.gate_run(self.root, run["id"], run["gate_token"][str(run["rounds"]["build"])])

    def commit(self, repo, rel, text, msg="FEAT: add thing"):
        p = self.root / repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        sh(self.root / repo, "git", "add", rel)
        sh(self.root / repo, "git", "commit", "-qm", msg)

    def set_profile(self, **changes):
        prof = json.loads((self.root / ".factory/profile.json").read_text())
        prof.update(changes)
        write_json(self.root / ".factory/profile.json", prof)

    def to_review(self, extra_files=(), before_gate=None, builder_skills=(E.UI_SKILL,)):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        for rel in extra_files:
            self.commit("svc", rel, "x\n", f"FEAT: add {rel}")
        self.agent_returns("builder", DONE, skills=builder_skills)
        self.next()
        if before_gate:
            before_gate()
        self.run_gate()
        return self.next()

    def prompt_of(self, act):
        prompt = act["agents"][0]["prompt"].splitlines()[1]
        path = prompt.removeprefix("Read the prompt at ").split(" and follow it exactly.", 1)[0]
        return Path(ast.literal_eval(path)).read_text()

    def ticket(self, n):
        return (self.root / f"docs/issues/eff/issues/0{n}-{'thing' if n == 1 else 'other'}.md").read_text()



class FactoryFlow(FlowBase):
    def review_plan(self, root, target, decision="approved", *, edit=None, expected_files=None):
        def review(command, **kwargs):
            self.assertEqual(command[1], "annotate")
            self.assertIn("--require-approval", command)
            if expected_files is not None:
                files = command[2:command.index("--gate")]
                self.assertEqual([Path(p).name for p in files], expected_files)
                self.assertTrue(all(Path(p).is_file() for p in files))
            if edit:
                edit()
            write_json(Path(command[-1]), {"decision": decision, "feedback": "Use a smaller scope."})
            return subprocess.CompletedProcess(command, 0 if decision == "approved" else 1)

        with unittest.mock.patch.object(A.shutil, "which", return_value="/usr/bin/plannotator"), \
                unittest.mock.patch.object(A.subprocess, "run", side_effect=review):
            return A.review(root, target)

    def test_board_and_queue_require_the_reviewed_ticket_versions(self):
        cfg = P.load(self.root)["tracker"]
        self.set_profile(tracker={**cfg, "require_plan_review": True})
        effort = self.root / "docs/issues/eff"
        (effort / "contract.md").write_text("Preserve an observable outcome.\n")
        revision = T.contract_revision(self.root, cfg, "eff")
        for path in (effort / "issues").glob("*.md"):
            path.write_text(T.field_text(path.read_text(), "Contract", revision))
        self.assertEqual([row["ref"] for row in E.board(self.root)["Plan review"]], ["eff/01", "eff/02"])
        self.assertIn("needs Plannotator plan approval", E.next_action(self.root, "eff/01")["reason"])
        result = self.review_plan(self.root, "eff", expected_files=["contract.md", "01-thing.md", "02-other.md"])
        self.assertEqual(result["tickets"], ["eff/01", "eff/02"])
        self.assertEqual(len(E.board(self.root)["Backlog"]), 2)
        path = "docs/issues/eff/issues/01-thing.md"
        T.comment(self.root, path, "A status note after approval.")
        self.assertEqual(len(E.board(self.root)["Backlog"]), 2)
        file = self.root / path
        file.write_text(file.read_text().replace("Add thing 1.", "Add a different thing."))
        self.assertEqual(E.board(self.root)["Plan review"][0]["ref"], "eff/01")
        self.assertIn("needs Plannotator plan approval", E.next_action(self.root, "eff/01")["reason"])
        (effort / "contract.md").write_text("Use revised shared behavior.\n")
        revision = T.contract_revision(self.root, cfg, "eff")
        for path in (effort / "issues").glob("*.md"):
            path.write_text(T.field_text(path.read_text(), "Contract", revision))
        self.assertEqual([row["ref"] for row in E.board(self.root)["Plan review"]], ["eff/01", "eff/02"])

    def test_changes_and_dismissal_keep_finished_plans_out_of_the_queue(self):
        path = "docs/issues/eff/issues/01-thing.md"
        T.set_status(self.root, path, "needs-plan-review")
        self.assertEqual(self.review_plan(self.root, "eff/01", "dismissed")["decision"], "dismissed")
        self.assertIn("Status: needs-plan-review", self.ticket(1))
        self.assertEqual(self.review_plan(self.root, "eff/01", "annotated")["decision"], "annotated")
        self.assertIn("Status: plan-changes", self.ticket(1))
        self.assertIn("Use a smaller scope.", self.ticket(1))
        T.set_status(self.root, path, "open")
        self.assertIn("needs Plannotator plan approval", E.next_action(self.root, "eff/01")["reason"])

    def test_approval_is_refused_when_a_ticket_changes_while_the_review_is_open(self):
        path = self.root / "docs/issues/eff/issues/01-thing.md"
        T.set_status(self.root, str(path), "needs-plan-review")
        update = path.read_text() + "\nNew scope.\n"
        with self.assertRaisesRegex(FactoryError, "Plans changed during review"):
            self.review_plan(self.root, "eff/01", edit=lambda: path.write_text(update))
        self.assertEqual(path.read_text(), update)

    def test_actions_run_from_paths_with_spaces(self):
        root = self.root.with_name("Work Space")
        self.root.rename(root)
        self.root = root
        os.environ["CLAUDE_PROJECT_DIR"] = str(root)
        bin_path = Path(self.tmp.name) / "Factory Tools" / "factory"
        bin_path.parent.mkdir()
        bin_path.symlink_to(E.FACTORY_BIN)

        def execute(action, text=None):
            return subprocess.run(action["cmd"], shell=True, cwd=root, input=text, text=True,
                                  capture_output=True, check=True, timeout=30).stdout

        with unittest.mock.patch.object(E, "FACTORY_BIN", bin_path):
            self.assertIn(str(root), self.prompt_of(self.next()))
            waiting = self.next()
            with unittest.mock.patch.object(E, "overdue", return_value=True):
                capture = self.next()
            self.assertIn("recorded research", execute(capture, BRIEF))
            self.assertEqual(execute(waiting).strip(), "DONE")
            self.assertEqual(self.next()["action"], "SPAWN")
            self.commit("svc", "thing.txt", "thing\n")
            self.agent_returns("builder", DONE)
            self.assertTrue(execute(self.next()).startswith("PASS"))

    def test_duplicate_ticket_number_blocks_candidates_and_dependents(self):
        issues = self.root / "docs/issues/eff/issues"
        (issues / "01-zed.md").write_text(TICKET.format(n=1, blocked="-").replace("open", "resolved"))
        (issues / "02-other.md").write_text(TICKET.format(n=2, blocked="01"))
        act = self.next()
        self.assertEqual(act["action"], "IDLE")
        self.assertIn("eff/01: duplicate ticket number", act["summary"])
        self.assertIn("eff/02: ambiguous dependency eff/01", act["summary"])
        self.assertIn("ambiguous ticket eff/01", E.next_action(self.root, "eff/01")["reason"])

    def test_missing_dependency_is_reported_without_blocking_other_tickets(self):
        issues = self.root / "docs/issues/eff/issues"
        self.assertIn("eff/02: missing dependency eff/03", E.status_lines(self.root))
        self.assertEqual(self.next()["action"], "SPAWN")
        self.assertEqual(self.active()["ticket"], str((issues / "01-thing.md").relative_to(self.root)))

    def test_concurrent_queue_commands_do_not_claim_two_tickets(self):
        second_ticket = self.root / "docs/issues/eff/issues/02-other.md"
        second_ticket.write_text(TICKET.format(n=2, blocked="-"))
        entered, resume = threading.Event(), threading.Event()
        original = E.new_run

        def hold_first(root, profile, ticket, stack):
            if ticket.number == "01":
                entered.set()
                if not resume.wait(5):
                    raise TimeoutError("Test did not release the first queue command")
            return original(root, profile, ticket, stack)

        first = {}
        with unittest.mock.patch.object(E, "new_run", side_effect=hold_first):
            worker = threading.Thread(target=lambda: first.update(E.next_action(self.root, "eff/01")))
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                second = E.next_action(self.root, "eff/02")
                self.assertEqual(second["action"], "STOP")
                self.assertIn("Another factory command", second["reason"])
            finally:
                resume.set()
                worker.join(5)
        self.assertEqual(first["action"], "SPAWN")
        self.assertEqual(self.active()["ticket_ref"], "eff/01")
        self.assertEqual(len(E.all_runs(self.root)), 1)
        self.assertIn("Status: open", second_ticket.read_text())
        retry = E.next_action(self.root, "eff/02")
        self.assertEqual(retry["action"], "STOP")
        self.assertIn("eff/01 is active", retry["reason"])

    def test_queue_recovers_if_interrupted_before_publishing_the_active_run(self):
        path = self.root / "docs/issues/eff/issues/01-thing.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        with unittest.mock.patch.object(E, "set_active", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.next()
        self.assertIn("Status: open", self.ticket(1))
        self.assertIsNone(E.state(self.root)["active"])
        draft = E.all_runs(self.root)[0]["id"]

        action = self.next()
        self.assertEqual((action["action"], action["run"]), ("SPAWN", draft))
        self.assertIn(b"Status: claimed\r\n", path.read_bytes())
        self.assertEqual(len(E.all_runs(self.root)), 1)

    def test_queue_recovers_if_interrupted_after_writing_the_claim(self):
        original = T.set_status

        def interrupt_after_write(*args, **kwargs):
            original(*args, **kwargs)
            raise SystemExit()

        with unittest.mock.patch.object(T, "set_status", side_effect=interrupt_after_write):
            with self.assertRaises(SystemExit):
                self.next()
        self.assertIn("Status: claimed", self.ticket(1))
        active = self.active()["id"]

        action = self.next()
        self.assertEqual((action["action"], action["run"]), ("SPAWN", active))
        self.assertEqual(len(E.all_runs(self.root)), 1)

    def test_resuming_a_claim_preserves_an_intervening_ticket_edit(self):
        with unittest.mock.patch.object(E, "set_active", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.next()
        path = self.root / "docs/issues/eff/issues/01-thing.md"
        updated = path.read_text() + "\n## Acceptance\nUse the updated requirements.\n"
        path.write_text(updated)

        action = self.next()
        self.assertEqual(action["action"], "STOP")
        self.assertIn("ticket changed", action["reason"])
        self.assertEqual(path.read_text(), updated)
        self.assertEqual(self.active()["outcome"], "needs-human")

    def test_status_reports_a_claim_from_an_older_interruption(self):
        path = "docs/issues/eff/issues/01-thing.md"
        T.set_status(self.root, path, "claimed")
        self.assertIn("eff/01: claimed without an active factory run", E.status_lines(self.root))
        self.assertIn("Status: claimed", self.ticket(1))

    def test_feature_evidence_matches_proofs_to_current_commits_and_contract(self):
        self.test_ticket_goes_from_queue_to_delivered_branch()
        svc = self.root / "svc"
        reviewed = E.git(svc, "rev-parse", "HEAD")
        evidence = E.feature_evidence(self.root, "eff")
        self.assertEqual(evidence["tickets"][0]["reviewed_heads"], {"svc": reviewed})
        self.assertEqual(evidence["tickets"][0]["delivery"], "reviewed commits present")
        self.assertEqual(evidence["tickets"][0]["gate"], "passed at delivery")
        self.assertEqual(evidence["tickets"][1]["delivery"], "unfinished")
        original_revision = evidence["tickets"][0]["ticket_revision"]
        path = self.root / evidence["tickets"][0]["path"]
        path.write_text(path.read_text() + "\n## Acceptance\nProve the current outcome.\n")
        self.assertNotEqual(E.feature_evidence(self.root, "eff")["tickets"][0]["ticket_revision"], original_revision)
        sh(svc, "git", "switch", "-q", "main")
        evidence = E.feature_evidence(self.root, "eff")
        self.assertEqual(evidence["tickets"][0]["delivery"], "reviewed commits need current proof")
        self.assertFalse(evidence["checkout"]["svc"]["dirty"])
        (self.root / "docs/issues/eff/contract.md").write_text("A new requirement.\n")
        evidence = E.feature_evidence(self.root, "eff")
        self.assertEqual(evidence["tickets"][0]["delivery"], "previous contract")

    def test_independent_ticket_research_uses_its_own_base(self):
        self.test_ticket_goes_from_queue_to_delivered_branch()
        svc = self.root / "svc"
        delivered = E.git(svc, "rev-parse", "HEAD")
        self.assertTrue((svc / "thing.txt").is_file())
        path = self.root / "docs/issues/eff/issues/02-other.md"
        path.write_text(TICKET.format(n=2, blocked="-"))

        self.assertEqual(self.next()["action"], "SPAWN")
        base = E.git(svc, "rev-parse", "main")
        self.assertEqual(E.git(svc, "rev-parse", "HEAD"), base)
        self.assertFalse((svc / "thing.txt").exists())
        self.assertEqual(E.git(svc, "rev-parse", "feature/minor-thing"), delivered)
        self.agent_returns("researcher", BRIEF.replace("minor-thing", "minor-other"))
        self.assertEqual(self.next()["action"], "SPAWN")
        self.assertEqual(self.active()["base"]["svc"], base)

    def test_research_does_not_switch_away_from_ticket_or_profile_changes(self):
        sh(self.root, "git", "switch", "-qc", "feature/minor-tracker")
        path = self.root / "docs/issues/eff/notes.md"
        self.commit(".", str(path.relative_to(self.root)), "Effort notes\n", "DOCS: add effort notes")

        act = self.next()
        self.assertEqual(act["action"], "STOP")
        self.assertIn("changes the tracker or factory profile", act["reason"])
        self.assertEqual(E.git(self.root, "branch", "--show-current"), "feature/minor-tracker")
        self.assertIn("Status: open", self.ticket(1))
        self.assertFalse(E.runs_dir(self.root).exists())

    def test_gate_drift_uses_the_configured_research_base(self):
        svc = self.root / "svc"
        gates = [{"id": "svc:test", "repo": "svc", "cmd": "echo ' Tests  3 passed (3)'", "expect_tests": True}]
        self.set_profile(gates=gates, inputs={"svc/a.txt": None})
        P.verify(self.root, setup=False)
        baseline = P.load(self.root)
        sh(svc, "git", "switch", "-qc", "feature/minor-previous")
        self.commit("svc", "a.txt", "new gate input\n")

        P.verify(self.root, setup=False)
        act = self.next()
        self.assertEqual(act["action"], "STOP")
        self.assertIn("svc:test", act["reason"])
        self.assertEqual(E.git(svc, "branch", "--show-current"), "feature/minor-previous")
        self.assertFalse(E.runs_dir(self.root).exists())

        write_json(P.path(self.root), baseline)
        self.assertEqual(P.drift(self.root, P.load(self.root)), ["svc:test"])
        self.assertEqual(self.next()["action"], "SPAWN")
        self.assertEqual((svc / "a.txt").read_text(), "a\n")
        self.assertEqual(P.drift(self.root, P.load(self.root)), [])

    def test_fix_review_uses_previous_review_head(self):
        self.to_review()
        before = self.active()["reviewed_heads"]["svc"]
        self.agent_returns("reviewer", "VERDICT: CHANGES\n\n## Findings\n- [required] logic: fix it")
        self.next()
        self.commit("svc", "thing.txt", "fixed\n", "FIX: thing")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        act = self.next()
        self.assertIn(f"`svc`@`{before}`", self.prompt_of(act))
        self.assertNotEqual(self.active()["reviewed_heads"]["svc"], before)
        E.release(self.root, self.active()["id"], "review-2")
        self.assertIn(f"`svc`@`{before}`", self.prompt_of(self.next()))

    def test_builder_commit_outside_declared_repos_stops_run(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.commit(".", "unexpected.txt", "outside the brief\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("outside declared repos", self.ticket(1))

    def test_passing_gate_that_changes_source_is_rejected(self):
        prof = P.load(self.root)
        prof["gates"][0]["cmd"] = "echo changed > a.txt; echo ' Tests  3 passed (3)'"
        write_json(P.path(self.root), prof)
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        gate = read_json(E.latest_gate(self.root, self.active()))
        self.assertFalse(gate["ok"])
        self.assertTrue(any("uncommitted changes left: a.txt" in p for p in gate["problems"]))

    def test_a_commit_after_the_gate_gets_checked_before_review(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        run = self.active()
        token = run["gate_token"]["1"]
        svc = self.root / "svc"
        sh(svc, "git", "rm", "thing.txt")
        sh(svc, "git", "commit", "-qm", "FIX: remove the required file")
        self.assertEqual(self.next()["action"], "RUN")
        self.assertNotEqual(self.active()["gate_token"]["1"], token)
        self.run_gate()
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    def test_a_gate_cannot_pass_if_it_checks_a_moving_commit(self):
        prof = P.load(self.root)
        prof["gates"][0]["cmd"] = ("test -f thing.txt && git rm -q thing.txt && "
                                   "git commit -qm 'FIX: make concurrent change' && echo ' Tests  3 passed (3)'")
        write_json(P.path(self.root), prof)
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        gate = read_json(E.latest_gate(self.root, self.active()))
        self.assertFalse(gate["ok"])
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("checkout changed while the gates ran", self.ticket(1))

    def test_ticket_goes_from_queue_to_delivered_branch(self):
        act = self.next()
        self.assertEqual(act["action"], "SPAWN")
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertIn("Status: claimed", self.ticket(1))
        self.agent_returns("researcher", BRIEF)
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:builder")
        svc = self.root / "svc"
        self.assertEqual(subprocess.run(["git", "-C", svc, "branch", "--show-current"], capture_output=True,
                                        text=True).stdout.strip(), "feature/minor-thing")
        (svc / "thing.txt").write_text("thing\n")
        sh(svc, "git", "add", "thing.txt")
        sh(svc, "git", "commit", "-qm", "FEAT: add thing")
        self.agent_returns("builder", "VERDICT: DONE\n\n## Change\nAdded thing.txt.")
        act = self.next()
        self.assertEqual(act["action"], "RUN")
        self.run_gate()
        act = self.next()
        self.assertEqual([a["subagent_type"] for a in act["agents"]], ["factory:reviewer"])
        self.agent_returns("reviewer", "VERDICT: PASS\n\n## Findings\n- [nit] naming: fine")
        act = self.next()
        self.assertEqual(act["action"], "IDLE")          # 02 still waits for its other dependency
        self.assertIn("Status: ready-for-review", self.ticket(1))
        run = E.all_runs(self.root)[-1]
        archive = self.root / "docs/issues/eff/runs" / run["id"]
        pr = (archive / "pr.md").read_text()
        self.assertIn("FEAT: 01 - Thing 1", pr)
        self.assertIn("3 passed", pr)
        self.assertFalse((E.runs_dir(self.root) / run["id"]).exists())
        self.assertIn(str((archive / "pr.md").relative_to(self.root)), self.ticket(1))
        self.assertNotIn("log", read_json(archive / "gate-1.json")["results"][0])
        self.assertEqual(E.result(self.root, run, "research"), BRIEF)
        self.assertIn("[nit] naming", pr)

    def test_red_convention_sends_builder_back_with_feedback(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        svc = self.root / "svc"
        (svc / "thing.txt").write_text("contact admin@realcorp.de at 8.8.4.4\n")
        sh(svc, "git", "add", "thing.txt")
        sh(svc, "git", "commit", "-qm", "added thing")
        self.agent_returns("builder", "VERDICT: DONE\n\n## Change\nx")
        self.next()
        self.run_gate()
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:builder")
        run = E.load_run(self.root, E.state(self.root)["active"])
        feedback = Path(run["feedback"]).read_text()
        self.assertIn("commit subject 'added thing'", feedback)
        self.assertIn("e-mail address at realcorp.de", feedback)
        self.assertIn("public IP 8.8.4.4", feedback)

    def test_needs_info_parks_questions_in_the_ticket(self):
        self.next()
        self.agent_returns("researcher", BRIEF.replace("READY", "NEEDS-INFO") +
                           "\n## Questions\n1. Skip empty orgs (recommended) or show 'no data'?\n")
        self.assertEqual(self.next()["action"], "IDLE")
        text = self.ticket(1)
        self.assertIn("Status: needs-info", text)
        self.assertIn("Skip empty orgs", text)

    def test_answered_ticket_reuses_the_proven_research_from_its_last_run(self):
        self.test_needs_info_parks_questions_in_the_ticket()
        path = "docs/issues/eff/issues/01-thing.md"
        T.comment(self.root, path, "Show no data.", who="owner")
        T.set_status(self.root, path, "open")
        action = self.next()
        previous = Path(self.active()["previous_brief"])
        self.assertIn(str(previous), self.prompt_of(action))
        self.assertIn("Skip empty orgs", previous.read_text())

    def test_evaluation_promotes_once_to_the_development_checkout_queue(self):
        def cli(root, *args):
            return subprocess.run([sys.executable, str(E.FACTORY_BIN), "--root", str(root), *args],
                                  capture_output=True, check=True, text=True).stdout.strip()

        args = ("eval", "report", "--summary", "Retries lose their result", "--observed", "The result is missing.",
                "--expected", "The same result survives a retry.", "--check", "Replay two identical attempts.")
        oid = cli(self.root, *args)
        self.assertEqual(cli(self.root, *args), oid)
        self.assertIn("Retries lose their result", cli(self.root, "eval"))
        self.assertIn("Replay two identical attempts.", cli(self.root, "eval", "show", oid))

        target = self.root.parent / "factory-dev"
        init_repo(target)
        result = target / "result.txt"
        result.write_text("lost\n")
        sh(target, "git", "add", "result.txt")
        sh(target, "git", "commit", "-qm", "CHORE: reference behavior")
        profile = P.load(self.root)
        profile["tracker"] = {"root": "docs/work", "layout": "flat"}
        profile["repos"] = [{"path": ".", "base": "main"}]
        profile["gates"] = [{"id": "replay", "repo": ".", "cmd": 'test "$(cat result.txt)" = kept'}]
        write_json(target / ".factory/profile.json", profile)
        cli(self.root, "eval", "configure", str(target))
        direct = cli(self.root, *args, "--baseline", "Second attempt lost its result.").splitlines()
        self.assertEqual(direct[0], oid)
        promote = ("eval", "ticket", oid, "--checkout", str(target), "--baseline", "Second attempt lost its result.")
        ticket = Path(cli(self.root, *promote))
        self.assertEqual(str(ticket), direct[1])
        self.assertIn("Baseline: Second attempt lost its result.", ticket.read_text())
        self.assertEqual(cli(target, "queue"), "")
        self.review_plan(target, ticket.parent.name)
        self.assertIn("Retries lose their result", cli(target, "queue"))

        def record(action, text):
            self.assertEqual(action["action"], "SPAWN", action)
            prompt = action["agents"][0]["prompt"]
            fields = re.match(r"FACTORY RUN (\S+) RESULT (\S+) SPAWN (\d+)", prompt).groups()
            subprocess.run([sys.executable, str(E.FACTORY_BIN), "--root", str(target), "record", *fields],
                           input=text, capture_output=True, check=True, text=True)

        record(E.next_action(target), BRIEF.replace("REPOS: svc", "REPOS: ."))
        action = E.next_action(target)
        result.write_text("kept\n")
        sh(target, "git", "add", "result.txt")
        sh(target, "git", "commit", "-qm", "FIX: retain retry result")
        record(action, DONE)
        self.assertEqual(E.next_action(target)["action"], "RUN")
        run = E.load_run(target, action["run"])
        E.gate_run(target, run["id"], run["gate_token"]["1"])
        record(E.next_action(target), PASS)
        self.assertEqual(E.next_action(target)["action"], "IDLE")
        self.assertIn("Status: ready-for-review", ticket.read_text())
        self.assertEqual(cli(self.root, *promote), str(ticket))
        self.assertIn("Status: ready-for-review", ticket.read_text())
        self.assertEqual(cli(target, "queue"), "")

    def test_recording_an_evaluation_does_not_invalidate_an_active_review(self):
        self.to_review()
        V.report(self.root, "Slow test", "Tests ran twice.", "Reuse previous proof.", "Replay an unchanged gate.")
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: ready-for-review", self.ticket(1))

    def write_contract(self, text, stamp=()):
        effort = self.root / "docs/issues/eff"
        path = effort / "contract.md"
        path.write_text(text)
        revision = T.contract_revision(self.root, {"root": "docs/issues"}, "eff")
        for number in stamp:
            ticket = next((effort / "issues").glob(f"{number:02}-*.md"))
            body = re.sub(r"(?m)^Contract: .*\n", "", ticket.read_text())
            ticket.write_text(body.replace("Type: task\n", f"Type: task\nContract: {revision}\n"))
        return revision

    def test_contract_revision_holds_the_whole_effort_until_all_tickets_are_updated(self):
        self.write_contract("Value should be returned as text.\n", stamp=(1, 2))
        self.write_contract("Return an integer instead.\n", stamp=(1,))
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("feature contract needs reconciliation in eff/02", E.status_lines(self.root))
        self.assertEqual(E.next_action(self.root, "eff/01")["action"], "STOP")
        self.write_contract("Return an integer instead.\n", stamp=(2,))
        action = self.next()
        self.assertEqual(action["action"], "SPAWN")
        self.assertIn("contract.md", self.prompt_of(action))

    def test_active_review_cannot_deliver_after_the_effort_is_revised(self):
        self.write_contract("Add text.\n", stamp=(1, 2))
        self.to_review()
        rid = self.active()["id"]
        self.write_contract("Add an integer instead.\n", stamp=(1, 2))
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertEqual(E.load_run(self.root, rid)["outcome"], "needs-human")
        self.assertFalse((E.runs_dir(self.root) / rid / "pr.md").exists())

    def test_revised_contract_parks_a_previous_unmerged_delivery(self):
        self.write_contract("Add text.\n", stamp=(1, 2))
        self.to_review()
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        self.write_contract("Add an integer instead.\n", stamp=(1, 2))
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: ready-for-human", self.ticket(1))
        self.assertIn("used a previous feature contract", self.ticket(1))

    def test_build_does_not_start_gates_after_the_running_ticket_changes(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        rid = self.active()["id"]
        T.comment(self.root, "docs/issues/eff/issues/01-thing.md", "Different outcome now.", who="owner")
        self.agent_returns("builder", DONE)
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertEqual(E.load_run(self.root, rid)["outcome"], "needs-human")
        self.assertIn("The ticket changed during this run.", self.ticket(1))

    def test_missing_verdict_is_sent_back_once(self):
        self.next()
        out = H.subagent_stop(self.stop_event("researcher", "I looked around."))
        self.assertEqual(out["decision"], "block")

    def test_human_reopen_continues_on_branch_with_feedback(self):
        self.test_ticket_goes_from_queue_to_delivered_branch()
        T.set_status(self.root, "docs/issues/eff/issues/01-thing.md", "open")
        T.comment(self.root, "docs/issues/eff/issues/01-thing.md", "Wrong file name, call it thing.md", who="max")
        sh(self.root / "svc", "git", "switch", "-q", "main")
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:builder")
        run = E.load_run(self.root, E.state(self.root)["active"])
        self.assertIn("thing.md", Path(run["feedback"]).read_text())
        self.assertTrue(run.get("reopened_from"))

    def test_stacked_ticket_starts_at_reviewed_commit_and_parks_when_base_is_rejected(self):
        path = "docs/issues/eff/issues/02-other.md"
        (self.root / path).write_text(TICKET.format(n=2, blocked="01"))
        self.to_review()
        parent = self.active()
        self.agent_returns("reviewer", PASS)
        action = self.next()
        self.assertIn("Stacked research base in `svc`", self.prompt_of(action))
        self.assertEqual(E.git(self.root / "svc", "rev-parse", "HEAD"), parent["reviewed_heads"]["svc"])
        self.agent_returns("researcher", BRIEF.replace("minor-thing", "minor-other"))
        self.next()
        child = self.active()
        self.assertEqual(child["base"]["svc"], parent["reviewed_heads"]["svc"])
        self.commit("svc", "other.txt", "other\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        self.next()
        self.assertEqual(G.changed_files(self.root, child, "svc"), ["other.txt"])
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        pr = E.run_dir(self.root, child["id"]) / "pr.md"
        self.assertIn("stacked on `feature/minor-thing`", pr.read_text())

        T.set_status(self.root, parent["ticket"], "open")
        T.comment(self.root, parent["ticket"], "Fix the base behavior.", who="owner")
        self.assertEqual(self.next()["action"], "SPAWN")
        self.assertIn("Status: ready-for-human", self.ticket(2))
        self.assertIn("Base ticket eff/01 was rejected", self.ticket(2))
        self.assertTrue(pr.is_file())

    def test_ticket_waits_if_the_reviewed_dependency_branch_moved(self):
        self.to_review()
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        (self.root / "docs/issues/eff/issues/02-other.md").write_text(TICKET.format(n=2, blocked="01"))
        self.commit("svc", "unreviewed.txt", "late change\n")
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertEqual(E.next_action(self.root, "eff/02")["action"], "STOP")
        self.assertIn("Status: open", self.ticket(2))

    def test_candidates_must_contain_every_unmerged_dependency(self):
        repo = self.root / "svc"
        main = E.git(repo, "rev-parse", "main")
        latest, tickets = {}, {}
        for number, branch in (("01", "left"), ("02", "right")):
            ticket = T.Ticket(branch, "eff", number, branch, "task", "ready-for-review")
            sh(repo, "git", "switch", "-qc", branch, "main")
            self.commit("svc", f"{branch}.txt", f"{branch}\n")
            tickets[branch] = ticket
            latest[branch] = {"id": branch, "outcome": "delivered", "branch": branch,
                              "base": {"svc": main}, "reviewed_heads": {"svc": E.git(repo, "rev-parse", "HEAD")}}
        task = T.Ticket("task", "eff", "04", "task", "task", "open", ["01", "02"])
        self.assertIsNone(K.plan(self.root, task, tickets, latest, E.STATUS_DEFAULTS))

        sh(repo, "git", "switch", "-qc", "combined", "left")
        sh(repo, "git", "merge", "--no-edit", "right")
        combined = E.git(repo, "rev-parse", "HEAD")
        tickets["combined"] = T.Ticket("combined", "eff", "03", "combined", "task", "ready-for-review")
        latest["combined"] = {"id": "combined", "outcome": "delivered", "branch": "combined",
                              "base": {"svc": main}, "reviewed_heads": {"svc": combined},
                              "stacked_on": {"left": "left", "right": "right"}}
        task.blocked_by.append("03")
        plan = K.plan(self.root, task, tickets, latest, E.STATUS_DEFAULTS)
        self.assertEqual(plan["stack_bases"]["svc"]["head"], combined)
        self.assertEqual(plan["stacked_on"], {"left": "left", "right": "right", "combined": "combined"})

    def test_started_agent_is_awaited_not_replaced(self):
        self.next()
        for _ in range(3):
            act = self.next()
            self.assertEqual(act["action"], "RUN")
            self.assertIn(" wait ", act["cmd"])
        rid = E.state(self.root)["active"]
        self.assertTrue(E.wait_agents(self.root, rid, wait=0).startswith("RUNNING research"))
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(E.wait_agents(self.root, rid, wait=0), "DONE")
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    def test_result_file_without_proof_is_ignored(self):
        self.next()
        rid = E.state(self.root)["active"]
        for name in ("research.md", "research@1.md"):
            (self.root / ".factory/runs" / rid / name).write_text(BRIEF)
        self.assertTrue(E.wait_agents(self.root, rid, wait=0).startswith("RUNNING research#1"))
        self.assertEqual(self.next()["action"], "RUN")
        self.agent_returns("researcher", BRIEF)
        out = subprocess.run([sys.executable, str(E.FACTORY_BIN), "--root", str(self.root), "wait", rid],
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "DONE")

    def age_spawns(self):
        rid = E.state(self.root)["active"]
        run = E.load_run(self.root, rid)
        for e in run["events"]:
            if e["event"] == "spawn":
                e["t"] = "2020-01-01T00:00:00+00:00"
        E.save_run(self.root, run)
        return rid

    def test_working_agents_are_awaited_past_the_idle_limit(self):
        self.next()
        self.age_spawns()
        read = {"tool_name": "Read", "tool_input": {"file_path": "x"}, "cwd": str(self.root),
                "agent_type": "factory:researcher"}
        self.assertIsNone(H.guard(read))
        self.assertEqual(self.next()["action"], "RUN")
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    def test_overdue_agent_is_recorded_then_stops_without_a_second_agent(self):
        self.next()
        rid = self.age_spawns()
        beat = self.root / ".factory/beat"
        beat.touch()
        old = time.time() - (E.AGENT_IDLE_MIN + 1) * 60
        os.utime(beat, (old, old))
        self.assertEqual(self.next()["action"], "RECORD")
        act = self.next()
        self.assertEqual(act["action"], "STOP")
        self.assertEqual(self.next()["action"], "STOP")
        spawns = lambda: [e for e in E.load_run(self.root, rid)["events"] if e["event"] == "spawn"]
        self.assertEqual(len(spawns()), 1)
        release = re.search(r"`([^`]+ release [^`]+)`", act["reason"]).group(1)
        subprocess.run(release.split(), cwd=self.root, check=True, capture_output=True)
        act = self.next()
        self.assertEqual(act["action"], "SPAWN")
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertEqual(len(spawns()), 2)
        self.assertEqual(self.next()["action"], "RUN")

    def test_wait_names_the_reviewer_still_missing(self):
        prof = json.loads((self.root / ".factory/profile.json").read_text())
        prof["review"] = {"security_paths": ["svc/*"]}
        write_json(self.root / ".factory/profile.json", prof)
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.assertEqual(self.next()["action"], "RUN")          # builder still working: no second builder
        rid = E.state(self.root)["active"]
        builders = [e for e in E.load_run(self.root, rid)["events"] if e["event"] == "spawn" and e["role"] == "builder"]
        self.assertEqual(len(builders), 1)
        svc = self.root / "svc"
        (svc / "thing.txt").write_text("thing\n")
        sh(svc, "git", "add", "thing.txt")
        sh(svc, "git", "commit", "-qm", "FEAT: add thing")
        self.agent_returns("builder", "VERDICT: DONE\n\n## Change\nAdded thing.txt.")
        self.next()
        self.run_gate()
        act = self.next()
        self.assertEqual([a["subagent_type"] for a in act["agents"]], ["factory:reviewer", "factory:security"])
        self.agent_returns("reviewer", "VERDICT: PASS\n\n## Findings\n- [nit] naming: fine")
        rid = E.state(self.root)["active"]
        self.assertTrue(E.wait_agents(self.root, rid, wait=0).startswith("RUNNING security-1#"))
        self.assertEqual(self.next()["action"], "RUN")

    # ---- review verdicts (F1) ----

    def test_review_without_a_verdict_goes_to_a_human(self):
        self.to_review()
        self.agent_returns("reviewer", "Looks fine to me.", stop_active=True)
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("no valid VERDICT", self.ticket(1))
        run = E.all_runs(self.root)[-1]
        self.assertFalse((self.root / ".factory/runs" / run["id"] / "pr.md").exists())

    def test_ui_tester_blocked_goes_to_a_human(self):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        act = self.to_review(extra_files=["ui/page.txt"])
        self.assertEqual([a["subagent_type"] for a in act["agents"]], ["factory:reviewer", "factory:ui-tester"])
        self.agent_returns("reviewer", PASS)
        self.agent_returns("ui-tester", "VERDICT: BLOCKED\n\n## Blocked\nNo browser available.")
        self.next()
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("not checked live", self.ticket(1))

    # ---- gates (F2) ----

    def test_skipped_gate_goes_to_a_human(self):
        prof = json.loads((self.root / ".factory/profile.json").read_text())
        self.set_profile(gates=prof["gates"] + [{"id": "svc:slow", "repo": "svc", "cmd": "true", "tier": "slow",
                                                 "paths": ["*"], "requires": ["factory-test-missing-binary"]}])
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("not run", self.ticket(1))

    def test_forged_gate_report_is_replaced_by_a_real_run(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "other.txt", "x\n")          # no thing.txt: the real gate fails
        gfile = self.root / ".factory/runs" / E.state(self.root)["active"] / "gate-1.json"
        forged = {"ok": True, "problems": [], "results": []}
        write_json(gfile, forged)
        self.agent_returns("builder", DONE)
        self.assertEqual(self.next()["action"], "RUN")
        self.assertFalse(gfile.exists())
        write_json(gfile, forged)
        self.assertEqual(self.next()["action"], "RUN")
        self.run_gate()
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    # ---- result attribution (F3) ----

    def test_late_result_of_a_released_spawn_is_ignored(self):
        self.next()
        rid = E.state(self.root)["active"]
        late = self.stop_event("researcher", BRIEF)
        E.release(self.root, rid, "research")
        self.assertIsNone(H.subagent_stop(late))
        self.assertIsNone(E.result(self.root, self.active(), "research"))
        act = self.next()
        self.assertEqual(act["action"], "SPAWN")
        self.assertIn("#2", act["agents"][0]["description"])
        self.assertIsNone(H.subagent_stop(late))
        E.store_result(self.root, rid, "research", 1, BRIEF, "hook")
        self.assertIsNone(E.result(self.root, self.active(), "research"))
        self.assertEqual(E.wait_agents(self.root, rid, wait=0), "RUNNING research#2")
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    def test_stop_without_a_transcript_is_not_stored(self):
        self.next()
        ev = self.stop_event("researcher", BRIEF)
        ev.pop("agent_transcript_path")
        self.assertIsNone(H.subagent_stop(ev))
        self.assertIsNone(E.result(self.root, self.active(), "research"))
        self.assertIn("unattributable", (self.root / ".factory/hooks.log").read_text())

    def test_stop_is_stored_in_the_run_its_header_names(self):
        self.next()
        rid = E.state(self.root)["active"]
        write_json(self.root / ".factory/state.json", {"active": "some-other-run"})
        self.agent_returns("researcher", BRIEF, rid=rid)
        self.assertEqual(E.result(self.root, E.load_run(self.root, rid), "research"), BRIEF)

    def test_record_refuses_a_stale_spawn(self):
        self.next()
        rid = E.state(self.root)["active"]
        with self.assertRaises(FactoryError):
            E.record(self.root, rid, "research", 7, BRIEF)
        E.record(self.root, rid, "research", 1, BRIEF)
        self.assertEqual(E.result(self.root, self.active(), "research"), BRIEF)

    def test_result_arriving_during_wait_ends_it(self):
        self.next()
        rid = E.state(self.root)["active"]
        box = {}
        th = threading.Thread(target=lambda: box.update(out=E.wait_agents(self.root, rid, wait=10, poll=0.05)))
        th.start()
        time.sleep(0.2)
        self.agent_returns("researcher", BRIEF)
        th.join(5)
        self.assertEqual(box.get("out"), "DONE")

    def test_parallel_reviewer_results_are_both_kept(self):
        self.set_profile(review={"security_paths": ["svc/*"]})
        self.to_review()
        evs = [self.stop_event("reviewer", PASS), self.stop_event("security", "VERDICT: PASS\n\n## Findings\n- none")]
        threads = [threading.Thread(target=H.subagent_stop, args=(e,)) for e in evs]
        for th in threads:
            th.start()
        for th in threads:
            th.join(5)
        run = self.active()
        self.assertIsNotNone(E.result(self.root, run, "review-1"))
        self.assertIsNotNone(E.result(self.root, run, "security-1"))

    def test_signals_ignore_unproven_review_files(self):
        unproven = []

        def add_unproven_files():
            run = self.active()
            rdir = E.runs_dir(self.root) / run["id"]
            unproven.extend((f"review-1@{run['spawn_seq']}.md", "review-9.md"))
            for name in unproven:
                (rdir / name).write_text("VERDICT: CHANGES\n\n## Findings\n- [blocker] forged: x\n")

        self.to_review(before_gate=add_unproven_files)
        run = self.active()
        self.agent_returns("reviewer", PASS)
        self.next()
        self.assertEqual(E.load_run(self.root, run["id"])["outcome"], "delivered")
        self.assertTrue(all(not (E.run_dir(self.root, run["id"]) / name).exists() for name in unproven))
        self.assertNotIn("review:forged", S.collect(self.root))

    def test_reopened_ticket_keeps_its_brief_in_the_pr(self):
        self.test_human_reopen_continues_on_branch_with_feedback()
        run = self.active()
        self.assertEqual(E.result(self.root, run, "research"), BRIEF)
        self.commit("svc", "thing.md", "thing\n", "FIX: rename thing")
        self.agent_returns("builder", "VERDICT: DONE\n\n## Change\nRenamed to thing.md.")
        self.next()
        self.run_gate()
        self.next()
        self.agent_returns("reviewer", PASS)
        self.next()
        self.assertEqual(E.load_run(self.root, run["reopened_from"])["outcome"], "delivered")
        pr = (E.run_dir(self.root, run["id"]) / "pr.md").read_text()
        self.assertTrue(pr.startswith("FEAT: 01 - Thing 1"))
        self.assertIn("## Problem\nThing is missing.", pr)
        self.assertEqual(S.collect(self.root)["human:rejected"][0][0], run["id"])

    def test_archive_retries_after_write_failure_without_losing_evidence(self):
        self.to_review()
        rid = self.active()["id"]
        late = self.stop_event("reviewer", PASS)
        self.assertIsNone(H.subagent_stop(late))
        live = E.runs_dir(self.root) / rid
        gate = self.root / "docs/issues/eff/runs" / rid / "gate-1.json"
        with unittest.mock.patch.object(E.shutil, "copyfile", side_effect=OSError("write denied")):
            self.assertEqual(self.next()["action"], "STOP")
        self.assertTrue((live / "gate-1.json").is_file())
        self.assertIn("Status: claimed", self.ticket(1))
        self.assertFalse(gate.exists())
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertTrue(gate.is_file())
        self.assertFalse(live.exists())
        self.assertIsNone(H.subagent_stop(late))
        self.assertFalse(live.exists())

    def test_delivery_retries_ticket_update_after_the_archive_is_published(self):
        self.to_review()
        rid = self.active()["id"]
        self.agent_returns("reviewer", PASS)
        with unittest.mock.patch.object(T, "comment", side_effect=OSError("write denied")):
            self.assertEqual(self.next()["action"], "STOP")
        self.assertFalse((E.runs_dir(self.root) / rid).exists())
        self.assertTrue((E.run_dir(self.root, rid) / "pr.md").exists())
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("PR text:", self.ticket(1))

    def test_status_and_reopen_find_older_runtime_runs(self):
        self.test_ticket_goes_from_queue_to_delivered_branch()
        run = E.all_runs(self.root)[-1]
        E.run_dir(self.root, run["id"]).rename(E.runs_dir(self.root) / run["id"])
        self.assertIn(run["id"], E.status_lines(self.root))
        T.set_status(self.root, run["ticket"], "open")
        T.comment(self.root, run["ticket"], "Retain old feedback.", who="owner")
        self.assertIn("builder", self.next()["agents"][0]["subagent_type"])
        self.assertEqual(E.result(self.root, self.active(), "research"), BRIEF)

    def test_archive_keeps_available_ui_screenshot_and_proven_result(self):
        self.set_profile(review={"ui_paths": ["svc/thing.txt"]})
        self.to_review()
        run = self.active()
        with tempfile.TemporaryDirectory(prefix="factory-ui-", dir="/tmp") as folder:
            shot = Path(folder) / "screen.png"
            shot.write_bytes(b"test screenshot")
            text = f"VERDICT: PASS\n\n## Browser check\nBrowser: example browser\nScreen: desktop page\nObservation: visible\n\n## Screenshots\n- {shot}: desktop\n"
            self.agent_returns("ui-tester", text)
            self.agent_returns("reviewer", PASS)
            self.assertEqual(self.next()["action"], "IDLE")
        self.assertEqual(E.result(self.root, run, "ui-1"), text)
        archive = E.run_dir(self.root, run["id"])
        self.assertEqual((archive / "screenshots/ui-1/screen.png").read_bytes(), b"test screenshot")
        self.assertIn("(screenshots/ui-1/screen.png)", (archive / "pr.md").read_text())

    def test_archive_keeps_failed_gate_excerpt_for_learning(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "initial.txt", "initial\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        self.next()
        run = self.active()
        self.agent_returns("reviewer", PASS)
        self.next()
        evidence = S.collect(self.root)["gate:svc:test"]
        self.assertEqual(evidence[0][0], run["id"])
        self.assertIn("gate-1.json", evidence[0][1])

    def test_init_retains_failed_gate_log_and_removes_successful_log(self):
        self.set_profile(gates=[{"id": "good", "cmd": "echo OK", "repo": "."},
                                {"id": "bad", "cmd": "echo ERROR; exit 1", "repo": "."}])
        P.verify(self.root, setup=False)
        self.assertEqual([g["baseline"]["status"] for g in P.load(self.root)["gates"]], ["pass", "fail"])
        self.assertEqual([p.name for p in (self.root / ".factory/verify").iterdir()], ["bad.log"])

    def test_hook_log_rotation_does_not_invalidate_review(self):
        self.to_review()
        path = self.root / ".factory/hooks.log"
        old = path.read_text()
        with unittest.mock.patch.object(H, "HOOK_LOG_LIMIT", len(old)):
            self.agent_returns("reviewer", PASS)
        self.assertEqual(path.with_name("hooks.log.1").read_text(), old)
        self.assertIn("stored review-1", path.read_text())
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: ready-for-review", self.ticket(1))

    def test_runs_with_identical_timestamps_get_distinct_ids(self):
        clock = E.datetime.datetime
        with unittest.mock.patch.object(E.datetime, "datetime", wraps=clock) as mocked:
            mocked.now.return_value = clock.now()
            first = E.allocate_run_id(self.root, "01-eff")
            second = E.allocate_run_id(self.root, "01-eff")
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(p.name for p in E.runs_dir(self.root).iterdir()), [first, second])

    def test_stop_hook_attributes_runs_from_efforts_with_spaces(self):
        tracker = self.root / "docs/issues"
        (tracker / "eff").rename(tracker / "legacy effort..v1")
        sh(self.root, "git", "add", "docs/issues")
        sh(self.root, "git", "commit", "-qm", "CHORE: legacy effort fixture")
        self.assertEqual(self.next()["action"], "SPAWN")
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(E.result(self.root, self.active(), "research"), BRIEF)
        self.assertEqual(self.next()["action"], "SPAWN")
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        self.next()
        self.agent_returns("reviewer", PASS)
        self.assertEqual(self.next()["action"], "IDLE")
        run = E.all_runs(self.root)[-1]
        self.assertEqual(run["outcome"], "delivered")
        self.assertTrue((tracker / "legacy effort..v1/runs" / run["id"] / "pr.md").is_file())
        T.set_status(self.root, run["ticket"], "open")
        T.comment(self.root, run["ticket"], "Clarify the expected result.", who="owner")
        self.assertIn("builder", self.next()["agents"][0]["subagent_type"])

    def test_respawned_reviewer_keeps_the_phase_fingerprint(self):
        self.set_profile(review={"security_paths": ["svc/*"]})
        self.to_review()
        rid = E.state(self.root)["active"]
        late = self.stop_event("security", "VERDICT: PASS\n\n## Findings\n- none")
        E.release(self.root, rid, "review-1")
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:reviewer")
        self.assertIsNone(H.subagent_stop(late))             # the other reviewer finishes after the respawn
        self.agent_returns("reviewer", PASS)
        self.next()
        self.assertIn("Status: ready-for-review", self.ticket(1))

    def test_result_edited_after_storage_counts_as_missing(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        run = self.active()
        E.result_path(self.root, run, "research").write_text(BRIEF.replace("READY", "NEEDS-INFO"))
        self.assertIsNone(E.result(self.root, run, "research"))

    def test_record_from_the_cli_reads_stdin(self):
        self.next()
        rid = E.state(self.root)["active"]
        out = subprocess.run([sys.executable, str(E.FACTORY_BIN), "--root", str(self.root), "record", rid, "research", "1"],
                             input=BRIEF, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertEqual(E.result(self.root, self.active(), "research"), BRIEF)

    def test_concurrent_gate_commands_share_one_fresh_report(self):
        invocations = Path(self.tmp.name) / "gate-invocations"
        prof = P.load(self.root)
        command = prof["gates"][0]["cmd"]
        prof["gates"][0]["cmd"] = f"echo run >> {E.shlex.quote(str(invocations))} && {command}"
        write_json(P.path(self.root), prof)
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        rid = E.state(self.root)["active"]
        write_json(self.root / ".factory/runs" / rid / "gate-1.json", {"ok": False, "problems": [], "results": []})
        with ThreadPoolExecutor(max_workers=2) as pool:
            callers = [pool.submit(E.gate, self.root, rid, wait=10) for _ in range(2)]
            for caller in callers:
                self.assertTrue(caller.result(timeout=15).startswith("PASS"))
        self.assertEqual(invocations.read_text(), "run\n")
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:reviewer")

    # ---- read-only agents (F4) ----

    def test_researcher_commit_in_the_parent_repo_is_detected(self):
        self.next()
        self.commit(".", "notes.txt", "x\n", "CHORE: notes")
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("workspace changed", self.ticket(1))

    def assert_review_tamper(self, tamper, before_gate=None):
        self.to_review(before_gate=before_gate)
        tamper()
        self.agent_returns("reviewer", PASS)
        self.next()
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("workspace changed", self.ticket(1))

    def test_reviewer_edit_to_the_running_ticket_is_detected(self):
        self.assert_review_tamper(lambda: (self.root / "docs/issues/eff/issues/01-thing.md").write_text(
            self.ticket(1) + "\nextra\n"))

    def test_human_edit_to_another_ticket_does_not_stop_the_run(self):
        self.to_review()
        (self.root / "docs/issues/eff/issues/02-other.md").write_text(TICKET.format(n=2, blocked="01") + "\nanswer\n")
        self.agent_returns("reviewer", PASS)
        self.next()
        self.assertIn("Status: ready-for-review", self.ticket(1))

    def test_reviewer_file_outside_the_run_repos_is_detected(self):
        self.assert_review_tamper(lambda: (self.root / "notes.txt").write_text("x\n"))

    def test_reviewer_edit_to_the_gate_report_is_detected(self):
        def tamper():
            g = self.root / ".factory/runs" / E.state(self.root)["active"] / "gate-1.json"
            g.write_text(g.read_text().replace('"ok": true', '"ok": true ').replace("passed", "PASSED"))
        self.assert_review_tamper(tamper)

    def test_reviewer_edit_to_an_already_dirty_file_is_detected(self):
        self.assert_review_tamper(lambda: (self.root / "scratch.txt").write_text("after\n"),
                                  before_gate=lambda: (self.root / "scratch.txt").write_text("before\n"))

    def test_reviewer_edit_to_an_untracked_plugin_file_is_detected(self):
        plugin = Path(self.tmp.name) / "plugin"
        (plugin / "roles").mkdir(parents=True)
        sh(plugin, "git", "init", "-q")
        (plugin / "roles/x.md").write_text("a\n")
        old, E.PLUGIN_ROOT = E.PLUGIN_ROOT, plugin
        try:
            self.assert_review_tamper(lambda: (plugin / "roles/x.md").write_text("b\n"))
        finally:
            E.PLUGIN_ROOT = old

    # ---- learning (F5) ----

    def test_learning_waits_for_a_clean_factory_checkout(self):
        plugin = Path(self.tmp.name) / "plugin"
        init_repo(plugin)
        (plugin / "x.md").write_text("x\n")
        sh(plugin, "git", "add", ".")
        sh(plugin, "git", "commit", "-qm", "CHORE: init")
        (plugin / "x.md").write_text("dirty\n")
        old_root, old_sig = E.PLUGIN_ROOT, S.pending_signals
        E.PLUGIN_ROOT, S.pending_signals = plugin, (lambda root: [("gate:x", {"runs": ["r1", "r2"], "digest": "d"})])
        try:
            act = self.next()
        finally:
            E.PLUGIN_ROOT, S.pending_signals = old_root, old_sig
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertIn("learning skipped", act.get("note", ""))

    # ---- UI retest (F6) ----

    def test_ui_tester_retests_after_a_backend_only_fix(self):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        act = self.to_review(extra_files=["ui/page.txt"])
        self.assertIn("factory:ui-tester", [a["subagent_type"] for a in act["agents"]])
        self.agent_returns("reviewer", PASS)
        self.agent_returns("ui-tester", "VERDICT: CHANGES\n\n## Findings\n- [required] ui: button hidden")
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")
        self.commit("svc", "api.txt", "fix\n", "FIX: api returns the button flag")
        self.agent_returns("builder", "VERDICT: DONE\n\n## Change\nFixed the flag.")
        self.next()
        self.run_gate()
        act = self.next()
        self.assertEqual([a["subagent_type"] for a in act["agents"]], ["factory:reviewer", "factory:ui-tester"])

    # ---- UI skill rule ----

    def ui_build(self, skills=()):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "thing.txt", "thing\n")
        self.commit("svc", "ui/page.txt", "page\n", "FEAT: add page")
        self.agent_returns("builder", DONE, skills=skills)
        return self.next()

    def test_ui_round_with_the_skill_goes_to_the_gate(self):
        self.ui_build(skills=["plugin:" + E.UI_SKILL])
        self.assertEqual(self.active()["stage"], "gate")

    def test_ui_round_without_the_skill_gets_one_reminder_round(self):
        act = self.ui_build(skills=["caveman"])
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:builder")
        feedback = Path(self.active()["feedback"]).read_text()
        self.assertIn("svc/ui/page.txt", feedback)
        self.assertIn(E.UI_SKILL, feedback)
        self.agent_returns("builder", DONE, skills=[E.UI_SKILL])     # nothing to change, but the skill is loaded
        self.next()
        self.assertEqual(self.active()["stage"], "gate")

    def test_second_ui_skill_miss_goes_to_a_human(self):
        self.ui_build()
        self.agent_returns("builder", DONE)     # the reminder round changes nothing and still skips the skill
        self.assertEqual(self.next()["action"], "IDLE")
        self.assertIn("Status: needs-human", self.ticket(1))
        self.assertIn("reminder round", self.ticket(1))

    def test_ui_result_without_transcript_is_not_verifiable(self):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.commit("svc", "ui/page.txt", "page\n", "FEAT: add page")
        run = self.active()
        E.record(self.root, run["id"], "build-1", run["spawn_ids"]["build-1"], DONE)
        self.next()
        self.assertIn("cannot be verified", Path(self.active()["feedback"]).read_text())

    def test_cli_ui_handoff_is_bound_to_prompt_and_spawn(self):
        skill = Path(self.tmp.name) / "skill.md"
        skill.write_text("---\nname: emil-design-eng\n---\nDesign carefully.\n")
        self.set_profile(review={"ui_paths": ["svc/ui/*"], "ui_skill_file": str(skill)})
        self.next()
        self.agent_returns("researcher", BRIEF + "\nUI: yes\n")
        self.next()
        run = self.active()
        prompt = E.runs_dir(self.root) / run["id"] / "prompts/build-1.md"
        self.assertIn("Design carefully.", prompt.read_text())
        self.commit("svc", "ui/page.txt", "page\n", "FEAT: add page")
        E.record(self.root, run["id"], "build-1", run["spawn_ids"]["build-1"], DONE + "\nUI-Skill-SHA256: " + E._file_sha(prompt))
        prompt.write_text(prompt.read_text() + "altered")
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")
        run = self.active()
        prompt = E.runs_dir(self.root) / run["id"] / "prompts/build-2.md"
        self.assertIn("Design carefully.", prompt.read_text())
        E.record(self.root, run["id"], "build-2", run["spawn_ids"]["build-2"], DONE + "\nUI-Skill-SHA256: " + E._file_sha(prompt))
        self.next()
        self.assertEqual(self.active()["stage"], "gate")

    def test_cli_ui_handoff_requires_attestation(self):
        skill = Path(self.tmp.name) / "skill.md"
        skill.write_text("---\nname: emil-design-eng\n---\nDesign carefully.\n")
        self.set_profile(review={"ui_paths": ["svc/ui/*"], "ui_skill_file": str(skill)})
        self.next()
        self.agent_returns("researcher", BRIEF + "\nUI: yes\n")
        self.next()
        run = self.active()
        self.commit("svc", "ui/page.txt", "page\n", "FEAT: add page")
        E.record(self.root, run["id"], "build-1", run["spawn_ids"]["build-1"], DONE)
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")
        self.assertIn("cannot be verified", Path(self.active()["feedback"]).read_text())

    def test_cli_ui_handoff_rejects_stale_attestation(self):
        skill = Path(self.tmp.name) / "skill.md"
        skill.write_text("---\nname: emil-design-eng\n---\nDesign carefully.\n")
        self.set_profile(review={"ui_paths": ["svc/ui/*"], "ui_skill_file": str(skill)})
        self.next()
        self.agent_returns("researcher", BRIEF + "\nUI: yes\n")
        self.next()
        run = self.active()
        old_digest = E._file_sha(E.runs_dir(self.root) / run["id"] / "prompts/build-1.md")
        self.commit("svc", "ui/page.txt", "page\n", "FEAT: add page")
        E.record(self.root, run["id"], "build-1", run["spawn_ids"]["build-1"], DONE)
        self.next()
        run = self.active()
        E.record(self.root, run["id"], "build-2", run["spawn_ids"]["build-2"], DONE + "\nUI-Skill-SHA256: " + old_digest)
        self.next()
        self.assertIn("reminder round did not change", self.ticket(1))

    def test_visual_ui_review_archives_both_same_named_screenshots(self):
        ticket = self.root / "docs/issues/eff/issues/01-thing.md"
        ticket.write_text(ticket.read_text().replace("Type: task", "Type: task\nUI-Proof: screenshots"))
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.to_review(extra_files=["ui/page.txt"])
        run = self.active()
        with tempfile.TemporaryDirectory(prefix="factory-ui-", dir="/tmp") as narrow, tempfile.TemporaryDirectory(prefix="factory-ui-", dir="/tmp") as wide:
            first, second = Path(narrow) / "screen.png", Path(wide) / "screen.png"
            first.write_bytes(b"narrow")
            second.write_bytes(b"wide")
            self.agent_returns("reviewer", PASS)
            self.agent_returns("ui-tester", f"VERDICT: PASS\n\n## Browser check\nBrowser: example browser\nScreen: page\nObservation: visible\nNarrow: 400px visible\nWide: 1200px visible\n\n## Screenshots\n- {first}: narrow page\n- {second}: wide page\n")
            self.assertEqual(self.next()["action"], "IDLE")
        captures = list((E.run_dir(self.root, run["id"]) / "screenshots/ui-1").iterdir())
        self.assertEqual({p.read_bytes() for p in captures}, {b"narrow", b"wide"})

    def test_ui_review_requires_browser_observation(self):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.to_review(extra_files=["ui/page.txt"])
        self.agent_returns("reviewer", PASS)
        self.agent_returns("ui-tester", "VERDICT: PASS\n\n## Browser check\nLooks good.")
        self.next()
        self.assertIn("no browser check", self.ticket(1))

    def test_small_ui_review_delivers_without_screenshots(self):
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.to_review(extra_files=["ui/page.txt"])
        self.agent_returns("reviewer", PASS)
        self.agent_returns("ui-tester", "VERDICT: PASS\n\n## Browser check\nBrowser: example browser\nScreen: page\nObservation: label visible")
        self.assertEqual(self.next()["action"], "IDLE")

    def test_visual_ui_review_rejects_one_screenshot(self):
        ticket = self.root / "docs/issues/eff/issues/01-thing.md"
        ticket.write_text(ticket.read_text().replace("Type: task", "Type: task\nUI-Proof: screenshots"))
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.to_review(extra_files=["ui/page.txt"])
        with tempfile.TemporaryDirectory(prefix="factory-ui-", dir="/tmp") as folder:
            shot = Path(folder) / "screen.png"
            shot.write_bytes(b"capture")
            self.agent_returns("reviewer", PASS)
            self.agent_returns("ui-tester", f"VERDICT: PASS\n\n## Browser check\nBrowser: example browser\nScreen: page\nObservation: visible\nNarrow: visible\nWide: visible\n\n## Screenshots\n- {shot}: narrow and wide page\n")
            self.next()
        self.assertIn("no required screenshots", self.ticket(1))

    def test_visual_ui_review_requires_screenshots(self):
        ticket = self.root / "docs/issues/eff/issues/01-thing.md"
        ticket.write_text(ticket.read_text().replace("Type: task", "Type: task\nUI-Proof: screenshots"))
        self.set_profile(review={"ui_paths": ["svc/ui/*"]})
        self.to_review(extra_files=["ui/page.txt"])
        self.agent_returns("reviewer", PASS)
        self.agent_returns("ui-tester", "VERDICT: PASS\n\n## Browser check\nBrowser: example browser\nScreen: page\nObservation: visible\nNarrow: page visible\nWide: page visible")
        self.next()
        self.assertIn("no required screenshots", self.ticket(1))

    # ---- models ----

    def models_of_round(self, brief, **profile):
        if profile:
            self.set_profile(**profile)
        self.next()
        self.agent_returns("researcher", brief)
        build = self.next()["agents"][0].get("model")
        self.commit("svc", "thing.txt", "thing\n")
        self.agent_returns("builder", DONE)
        self.next()
        self.run_gate()
        return build, {a["subagent_type"]: a.get("model") for a in self.next()["agents"]}

    def test_difficulty_picks_builder_and_reviewer_model(self):
        for line, level, model in (("DIFFICULTY: simple - one file", "simple", "sonnet"),
                                   ("**DIFFICULTY:** extreme", "extreme", "fable"),
                                   ("DIFFICULTY: medium   (simple, medium or extreme)", "medium", "opus")):
            with self.subTest(line=line):
                self.tearDown()
                self.setUp()
                build, review = self.models_of_round(BRIEF.replace("COMMIT_TYPE: FEAT", f"COMMIT_TYPE: FEAT\n{line}"))
                self.assertEqual((build, review["factory:reviewer"]), (model, model))
                self.assertEqual(self.active()["difficulty"], level)

    def test_missing_difficulty_falls_back_to_opus_and_the_profile_wins(self):
        build, review = self.models_of_round(BRIEF, models={"reviewer": "haiku"})
        self.assertEqual((build, review["factory:reviewer"]), ("opus", "haiku"))

    def test_security_spawn_leaves_the_model_to_its_agent_file(self):
        _, review = self.models_of_round(BRIEF, review={"security_paths": ["svc/*"]})
        self.assertIn("factory:security", review)
        self.assertIsNone(review["factory:security"])

    # ---- branches (F7) ----

    def test_refused_brief_is_retried_with_the_refusal(self):
        self.next()
        self.agent_returns("researcher", BRIEF.replace("feature/minor-thing", "bad-branch"))
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertIn("#2", act["agents"][0]["description"])
        self.assertIn("was refused", self.prompt_of(act))
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")

    def test_foreign_existing_branch_is_refused(self):
        sh(self.root / "svc", "git", "branch", "feature/minor-thing")
        self.next()
        self.agent_returns("researcher", BRIEF)
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertIn("already exists in svc", self.prompt_of(act))

    def test_branch_reuse_is_checked_per_repo(self):
        self.next()
        self.agent_returns("researcher", BRIEF)
        self.next()
        self.agent_returns("builder", "VERDICT: BLOCKED\n\n## Blocked\nNeeds a key.")
        self.assertEqual(self.next()["action"], "IDLE")
        T.set_status(self.root, "docs/issues/eff/issues/01-thing.md", "open")
        sh(self.root / "svc", "git", "switch", "-q", "main")
        sh(self.root, "git", "branch", "feature/minor-thing")
        self.next()
        self.agent_returns("researcher", BRIEF.replace("REPOS: svc", "REPOS: ., svc"))
        act = self.next()
        self.assertEqual(act["agents"][0]["subagent_type"], "factory:researcher")
        self.assertIn("already exists in .", self.prompt_of(act))
        self.agent_returns("researcher", BRIEF)
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:builder")
        self.assertEqual(subprocess.run(["git", "-C", self.root / "svc", "branch", "--show-current"],
                                        capture_output=True, text=True).stdout.strip(), "feature/minor-thing")

    # ---- profile drift (F8) ----

    def test_changed_inputs_stop_until_their_gates_are_reverified(self):
        self.set_profile(inputs={"svc/a.txt": None}, gates=[
            {"id": "svc:a", "repo": "svc", "cmd": "test -f a.txt && echo ' Tests  1 passed (1)'", "tier": "fast",
             "expect_tests": True},
            {"id": "svc:test", "repo": "svc", "cmd": "test -f thing.txt && echo ' Tests  3 passed (3)'",
             "tier": "fast", "expect_tests": True}])
        P.verify(self.root, setup=False)
        self.assertEqual(P.drift(self.root, P.load(self.root)), ["svc:test"])
        self.commit("svc", "a.txt", "changed\n", "CHORE: change a")
        self.assertEqual(P.drift(self.root, P.load(self.root)), ["svc:a", "svc:test"])
        P.verify(self.root, setup=False, setup_only=True)
        self.assertEqual(P.drift(self.root, P.load(self.root)), ["svc:a", "svc:test"])
        P.verify(self.root, only=["svc:a"], setup=False)
        self.assertEqual(P.drift(self.root, P.load(self.root)), ["svc:test"])
        act = self.next()
        self.assertEqual(act["action"], "STOP")
        self.assertIn("svc:test", act["reason"])


class Pure(unittest.TestCase):
    def test_detect_ci_commands_from_workflows(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workflow = root / ".github/workflows/test.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("""jobs:
  test:
    steps:
      - name: Test
        run: python3 -m unittest
      - run: python3 -m pytest
      - run: |-
          - not a command hint
          echo ignored
      - run: >+
          echo ignored too
      - run: | # tests
          echo ignored
      - run: |2
          echo ignored
      - run: >2- # folded
          echo ignored
      - run: |-2
          echo ignored
      - name: Next
        run: python3 -m compileall
""")
            (root / "bitbucket-pipelines.yml").write_text("""pipelines:
  default:
    - step:
        script:
          - 'python3 -m unittest'
          - python3 -m pytest
""")
            self.assertEqual(D.repo_facts(root, ".")["ci"], [
                "python3 -m unittest", "python3 -m pytest",
                "python3 -m unittest", "python3 -m pytest", "python3 -m compileall",
            ])

    def test_signing_needs_an_agent_unless_a_custom_signer_is_set(self):
        env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.dict(os.environ, env):
            os.environ.pop("SSH_AUTH_SOCK", None)
            repo = Path(d)
            init_repo(repo)
            for key, value in (("commit.gpgsign", "true"), ("gpg.format", "ssh"),
                               ("user.signingkey", "ssh-ed25519 AAAAtest")):
                sh(repo, "git", "config", key, value)
            self.assertIn("SSH_AUTH_SOCK", E.signing_problem(repo))
            sh(repo, "git", "config", "gpg.ssh.program", "/opt/1Password/op-ssh-sign")
            self.assertIsNone(E.signing_problem(repo))

    def test_summaries(self):
        self.assertEqual(G.parse_summary(" Tests  1 failed | 11 passed (12)"), {"passed": 11, "failed": 1, "errors": 0})
        self.assertEqual(G.parse_summary("Tests:       41 passed, 41 total"), {"passed": 41, "failed": 0, "errors": 0})
        self.assertEqual(G.parse_summary("==== 2 failed, 120 passed in 4.20s ===="), {"passed": 120, "failed": 2, "errors": 0})
        self.assertEqual(G.parse_summary("120 passed in 1.2s"), {"passed": 120, "failed": 0, "errors": 0})
        self.assertIsNone(G.parse_summary("all good"))
        self.assertEqual(G.parse_summary("Ran 10 tests in 0.3s\n\nFAILED (failures=1, errors=2)"),
                         {"passed": 7, "failed": 1, "errors": 2})
        self.assertEqual(G.parse_summary("Ran 4 tests in 0.1s\n\nOK"), {"passed": 4, "failed": 0, "errors": 0})

    def test_tenant_data_allows_documentation_ranges(self):
        diff = "+++ b/x.ts\n+const a = '192.0.2.4'; const b = 'ops@example.com'\n+const c = '93.184.216.34'\n"
        self.assertEqual(G.tenant_data_hits(diff), ["x.ts: public IP 93.184.216.34"])

    def test_guard_only_acts_on_factory_agents(self):
        push = {"tool_name": "Bash", "tool_input": {"command": "git -C svc push origin HEAD"}, "cwd": "/tmp"}
        self.assertIsNone(H.guard(push))
        out = H.guard({**push, "agent_type": "factory:builder"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        edit = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.py"}, "cwd": "/tmp", "agent_type": "factory:reviewer"}
        self.assertIn("read-only", H.guard(edit)["hookSpecificOutput"]["permissionDecisionReason"])
        protected = {"tool_name": "Edit", "tool_input": {"file_path": str(H.PLUGIN_ROOT / "lib/factory/gates.py")},
                     "cwd": "/tmp", "agent_type": "factory:learner"}
        self.assertEqual(H.guard(protected)["hookSpecificOutput"]["permissionDecision"], "deny")
        role = {**protected, "tool_input": {"file_path": str(H.PLUGIN_ROOT / "roles/builder.md")}}
        self.assertIn("read-only", H.guard(role)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_guard_denies_pushes_and_state_writes_but_not_reads_or_stash(self):
        bash = lambda cmd: H.guard({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp",
                                    "agent_type": "factory:builder"})
        for cmd in ("git push", "git -C svc push origin HEAD", "cd x && git -c a=b push", "echo x > .factory/state.json",
                    "echo x >> /r/.factory/runs/1/run.json", "rm -rf .factory/runs/1"):
            self.assertIsNotNone(bash(cmd), cmd)
        for cmd in ("git stash push src/a.ts -q && npx vitest run; git stash pop -q",
                    "ls -R .factory/runs/1 2>&1 | head -50", "git status 2>/dev/null; cat .factory/runs/1/run.json"):
            self.assertIsNone(bash(cmd), cmd)

    def test_drift_counts_only_a_gates_own_repo_and_root_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("a/x", "b/y", "ci.yml"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("1")
            prof = {"inputs": {"a/x": None, "b/y": None, "ci.yml": None},
                    "gates": [{"id": "a:t", "repo": "a"}, {"id": "b:t", "repo": "b"}, {"id": "all:t", "repo": "."}]}
            for g in prof["gates"]:
                g["baseline"] = {"inputs": P.input_hashes(root, prof)}
            self.assertEqual(P.drift(root, prof), [])
            (root / "a/x").write_text("2")
            self.assertEqual(P.drift(root, prof), ["a:t", "all:t"])
            (root / "ci.yml").write_text("2")
            self.assertEqual(P.drift(root, prof), ["a:t", "b:t", "all:t"])

    def test_frontier_respects_blockers_and_types(self):
        with tempfile.TemporaryDirectory() as d:
            issues = Path(d) / "docs/issues/e/issues"
            issues.mkdir(parents=True)
            (issues / "01-a.md").write_text("# a\nType: task\nStatus: resolved\nBlocked by: -\n")
            (issues / "02-b.md").write_text("# b\n**Type:** implementation\n**Status:** open\nBlocked by: 01\n")
            (issues / "03-c.md").write_text("# c\nType: grilling\nStatus: open\nBlocked by: -\n")
            (issues / "04-d.md").write_text("# d\nType: task\nStatus: open\nBlocked by: 03\n")
            cfg = E.tracker_cfg({"tracker": {"root": "docs/issues"}})
            self.assertEqual([t.number for t in T.frontier(d, cfg)], ["02"])
            T.set_status(d, "docs/issues/e/issues/02-b.md", "claimed")
            self.assertIn("**Status:** claimed", (issues / "02-b.md").read_text())

    def test_flat_tracker_orders_priority_and_ignores_the_old_plumbline_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = root / "docs/issues/old"
            old.mkdir(parents=True)
            (old / "01-old.md").write_text(TICKET.format(n=1, blocked="-"))
            self.assertEqual(D.tracker_facts(root)["tickets"], 0)
            new = root / "docs/work/new"
            new.mkdir(parents=True)
            (new / "01-normal.md").write_text(TICKET.format(n=1, blocked="-"))
            (new / "02-high.md").write_text(TICKET.format(n=2, blocked="-").replace("Type:", "Priority: high\nType:"))
            cfg = E.tracker_cfg({"tracker": {"root": "docs/work", "layout": "flat"}})
            self.assertEqual([t.ref for t in T.frontier(root, cfg)], ["new/02", "new/01"])
            self.assertEqual(D.tracker_facts(root)["layout"], "flat")


class Learner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin = Path(self.tmp.name) / "factory"
        init_repo(self.plugin)
        for rel in ("roles/builder.md", "lib/factory/gates.py"):
            (self.plugin / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.plugin / rel).write_text("x\n")
        sh(self.plugin, "git", "add", ".")
        sh(self.plugin, "git", "commit", "-qm", "CHORE: init")
        self._old = S.PLUGIN_ROOT
        S.PLUGIN_ROOT = self.plugin

    def tearDown(self):
        S.PLUGIN_ROOT = self._old
        self.tmp.cleanup()

    def head(self):
        return subprocess.run(["git", "-C", self.plugin, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_candidate_requires_one_allowed_file_and_exact_baseline(self):
        base = self.head()
        edit = {"path": "roles/builder.md", "old": "x\n", "new": "A better instruction.\n"}
        self.assertEqual(S.prepare_candidate(base, json.dumps(edit))["after"], edit["new"])
        for bad in ({"path": "roles/learner.md"}, {"path": "skills/eval/SKILL.md"},
                    {"path": "../roles/builder.md"}, {"old": "stale"}, {"new": ""}):
            with self.subTest(bad=bad), self.assertRaises(FactoryError):
                S.prepare_candidate(base, json.dumps({**edit, **bad}))

    def test_new_skill_requires_frontmatter(self):
        path = "skills/usable/SKILL.md"
        body = "---\nname: usable\ndescription: Verify a result.\norigin: learned\n---\n\nCheck the result.\n"
        edit = {"path": path, "old": None, "new": body}
        self.assertEqual(S.prepare_candidate(self.head(), json.dumps(edit))["after"], body)
        with self.assertRaisesRegex(FactoryError, "frontmatter"):
            S.prepare_candidate(self.head(), json.dumps({**edit, "new": "No frontmatter\n"}))

    def test_rejected_change_is_tried_not_covered(self):
        root = Path(self.tmp.name) / "proj"
        (root / ".factory").mkdir(parents=True)
        old = S.collect
        S.collect = lambda r: {"gate:x": [("r1", "e"), ("r2", "e")]}
        try:
            self.assertEqual([k for k, _ in S.pending_signals(root)], ["gate:x"])
            S.mark_tried(root, "gate:x", ["r1", "r2"], ["uncommitted change roles/builder.md"])
            self.assertEqual(S.pending_signals(root), [])
            self.assertNotIn("r1", read_json(root / ".factory/learn.json")["gate:x"]["runs"])
            S.collect = lambda r: {"gate:x": [("r1", "e"), ("r2", "e"), ("r3", "e"), ("r4", "e")]}
            self.assertEqual(S.pending_signals(root)[0][1]["runs"], ["r3", "r4"])
        finally:
            S.collect = old


class LearnRun(FlowBase):
    """advance_learn end to end with a throwaway factory repo."""

    def setUp(self):
        super().setUp()
        self.plugin = Path(self.tmp.name) / "factory"
        init_repo(self.plugin)
        (self.plugin / "roles").mkdir()
        (self.plugin / "roles/reviewer.md").write_text("x\n")
        sh(self.plugin, "git", "add", ".")
        sh(self.plugin, "git", "commit", "-qm", "CHORE: init")
        self._old = E.PLUGIN_ROOT, S.PLUGIN_ROOT, S.collect
        E.PLUGIN_ROOT = S.PLUGIN_ROOT = self.plugin
        S.collect = lambda root: {"gate:x": [("r1", "e"), ("r2", "e")]}

    def tearDown(self):
        E.PLUGIN_ROOT, S.PLUGIN_ROOT, S.collect = self._old
        super().tearDown()

    def propose(self, path="roles/reviewer.md"):
        self.next()
        self.agent_returns("learner", "VERDICT: CHANGED\n\n## Candidate\n" + json.dumps({
            "path": path, "old": "x\n", "new": "x\n- rule\n"}))

    def add_replay(self):
        write_json(self.plugin / "tests/learning.json", {"gate:x": {
            "path": "roles/reviewer.md", "cases": {
                "bad": {"prompt": "A failing change", "expected": "CHANGES"},
                "good": {"prompt": "A working change", "expected": "PASS"},
            },
        }})
        sh(self.plugin, "git", "add", "tests/learning.json")
        sh(self.plugin, "git", "commit", "-qm", "TEST: register held-out cases")

    def record_scores(self, **scores):
        self.agent_returns("reviewer", "VERDICT: REPLAYED\n\n## Results\n" + json.dumps(scores))

    def advance_learning(self):
        return E.next_action(self.root, learn_only=True)

    def test_builder_replay_scores_patches_and_rejects_regression(self):
        for regression in (False, True, "baseline", "checks"):
            (self.plugin / "roles/builder.md").write_text("x\n")
            fixture = self.plugin / "tests/fixtures/builder-replay"
            fixture.mkdir(parents=True)
            (fixture / "calc.py").write_text('def calculate(a, op, b):\n    return a + b\n')
            checks = self.plugin / "tests/fixtures/builder-checks.py"
            checks.write_text('import json, sys\nfrom pathlib import Path\n'
                              'exec((Path(sys.argv[1]) / "calc.py").read_text())\n'
                              'print(json.dumps({"add": calculate(7, "+", 4) == 11, '
                              '"sub": calculate(7, "-", 4) == 3}))\n')
            write_json(self.plugin / "tests/learning.json", {"gate:x": {
                "path": "roles/builder.md", "fixture": "tests/fixtures/builder-replay",
                "checks": "tests/fixtures/builder-checks.py", "task": "Add subtraction."}})
            sh(self.plugin, "git", "add", "roles/builder.md", "tests")
            sh(self.plugin, "git", "commit", "-qm", "TEST: builder replay")
            self.propose("roles/builder.md")
            action = self.advance_learning()
            self.assertEqual(action["action"], "SPAWN", E.all_runs(self.root)[-1])
            self.agent_returns("builder", "VERDICT: DONE")
            self.advance_learning()
            run = E.all_runs(self.root)[-1]
            checkout = E.runs_dir(self.root) / run["id"] / "builder-replay/replay-candidate"
            (checkout / "calc.py").write_text('def calculate(a, op, b):\n    return a - b' +
                                                ('\n' if regression is True else ' if op == "-" else a + b\n'))
            if regression == "baseline":
                (checkout.parent / "replay-baseline/calc.py").write_text("tampered\n")
            if regression == "checks":
                (checkout.parent / "checks.py").write_text("tampered\n")
            self.agent_returns("builder", "VERDICT: DONE")
            self.assertEqual(self.advance_learning()["action"], "IDLE")
            self.assertEqual(E.all_runs(self.root)[-1]["outcome"], "rejected" if regression else "changed")
            self.assertEqual((self.plugin / "roles/builder.md").read_text(), "x\n" if regression else "x\n- rule\n")
            self.tearDown()
            self.setUp()

    def test_builder_replay_rejects_missing_inputs(self):
        for missing in ("recipe.json", "checks.py", "replay-baseline"):
            (self.plugin / "roles/builder.md").write_text("x\n")
            fixture = self.plugin / "tests/fixtures/builder-replay"
            fixture.mkdir(parents=True)
            (fixture / "calc.py").write_text("value = 1\n")
            checks = self.plugin / "tests/fixtures/builder-checks.py"
            checks.write_text('import json\nprint(json.dumps({"old": False, "new": False}))\n')
            write_json(self.plugin / "tests/learning.json", {"gate:x": {
                "path": "roles/builder.md", "fixture": "tests/fixtures/builder-replay",
                "checks": "tests/fixtures/builder-checks.py", "task": "Add behavior."}})
            sh(self.plugin, "git", "add", "roles/builder.md", "tests")
            sh(self.plugin, "git", "commit", "-qm", "TEST: replay inputs")
            self.propose("roles/builder.md")
            self.advance_learning()
            run = E.all_runs(self.root)[-1]
            path = E.runs_dir(self.root) / run["id"] / "builder-replay" / missing
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            self.agent_returns("builder", "VERDICT: DONE")
            self.assertEqual(self.advance_learning()["action"], "IDLE")
            self.assertEqual(E.all_runs(self.root)[-1]["outcome"], "rejected")
            self.tearDown()
            self.setUp()

    def test_builder_fixture_checks_unsupported_operation(self):
        checks = Path(__file__).parent / "fixtures/builder-checks.py"
        with tempfile.TemporaryDirectory() as temp:
            calc = Path(temp) / "calc.py"
            calc.write_text('def calculate(a, op, b):\n'
                            '    if op == "+": return a + b\n'
                            '    if op == "-": return a - b\n'
                            '    raise ValueError("unsupported")\n')
            def score():
                return json.loads(subprocess.check_output([sys.executable, str(checks), temp], text=True))
            self.assertEqual(score(), {"addition": True, "subtraction": True, "unsupported": True})
            calc.write_text(calc.read_text().replace('raise ValueError("unsupported")', 'return 0'))
            self.assertEqual(score(), {"addition": True, "subtraction": True, "unsupported": False})

    def test_candidate_without_replay_stays_proposed_and_queue_continues(self):
        path = self.plugin / "roles/reviewer.md"
        self.propose()
        self.assertEqual(self.next()["agents"][0]["subagent_type"], "factory:researcher")
        self.assertEqual(path.read_text(), "x\n")
        entry = read_json(self.root / ".factory/learn.json")["gate:x"]
        self.assertEqual(entry["tried"], ["r1", "r2"])
        self.assertEqual(entry["runs"], [])
        self.assertEqual(entry["changes"][-1]["verdict"], "proposed")

    def test_only_candidate_that_improves_held_out_replay_is_adopted(self):
        self.add_replay()
        self.propose()
        path = self.plugin / "roles/reviewer.md"
        first = self.advance_learning()
        self.assertTrue(self.prompt_of(first).startswith("x\n\n"))
        self.assertNotIn('"CHANGES"', self.prompt_of(first))
        self.record_scores(bad="PASS", good="PASS")
        second = self.advance_learning()
        self.assertNotEqual(first["agents"][0]["prompt"], second["agents"][0]["prompt"])
        self.assertTrue(self.prompt_of(second).startswith("x\n- rule\n"))
        self.assertEqual(path.read_text(), "x\n")
        self.record_scores(bad="CHANGES", good="PASS")
        self.assertEqual(self.advance_learning()["action"], "IDLE")
        entry = read_json(self.root / ".factory/learn.json")["gate:x"]
        self.assertEqual(entry["runs"], ["r1", "r2"])
        self.assertEqual(entry["changes"][-1]["commit"], E.git(self.plugin, "rev-parse", "HEAD"))
        self.assertIn("- rule", path.read_text())
        self.assertEqual(E.git(self.plugin, "worktree", "list", "--porcelain").count("worktree "), 1)

    def test_replay_regression_leaves_live_role_intact(self):
        self.add_replay()
        self.propose()
        self.advance_learning()
        self.record_scores(bad="PASS", good="PASS")
        self.advance_learning()
        self.record_scores(bad="CHANGES", good="CHANGES")
        self.assertEqual(self.advance_learning()["action"], "IDLE")
        self.assertEqual((self.plugin / "roles/reviewer.md").read_text(), "x\n")
        entry = read_json(self.root / ".factory/learn.json")["gate:x"]
        self.assertEqual(entry["changes"][-1]["verdict"], "rejected")
        self.assertEqual(entry["runs"], [])

    def test_learning_skips_candidate_replay_when_baseline_already_passes(self):
        self.add_replay()
        self.propose()
        self.advance_learning()
        self.record_scores(bad="CHANGES", good="PASS")
        self.assertEqual(self.advance_learning()["action"], "IDLE")
        run = E.all_runs(self.root)[-1]
        self.assertNotIn("replay-candidate", run["spawn_ids"])
        self.assertIn("Baseline already passes", run["finish_reason"])

    def test_researcher_replay_outcomes(self):
        for baseline, candidate, outcome in [
            (("NEEDS-INFO", "NEEDS-INFO"), ("READY", "NEEDS-INFO"), "changed"),
            (("NEEDS-INFO", "NEEDS-INFO"), ("READY", "READY"), "rejected"),
            (("READY", "NEEDS-INFO"), None, "rejected"),
        ]:
            with self.subTest(outcome=outcome, baseline=baseline):
                self.setUp_researcher_replay()
                self.propose("roles/researcher.md")
                first = self.advance_learning()
                self.assertEqual(first["agents"][0]["subagent_type"], "factory:researcher")
                self.assertNotIn('"NEEDS-INFO"', self.prompt_of(first))
                self.agent_returns("researcher", "VERDICT: REPLAYED\n\n## Results\n" +
                                   json.dumps(dict(zip(("settled", "open"), baseline))))
                if candidate:
                    second = self.advance_learning()
                    self.assertTrue(self.prompt_of(second).startswith("x\n- rule\n"))
                    self.agent_returns("researcher", "VERDICT: REPLAYED\n\n## Results\n" +
                                       json.dumps(dict(zip(("settled", "open"), candidate))))
                self.assertEqual(self.advance_learning()["action"], "IDLE")
                self.assertEqual(E.all_runs(self.root)[-1]["outcome"], outcome)
                self.assertEqual((self.plugin / "roles/researcher.md").read_text(),
                                 "x\n- rule\n" if outcome == "changed" else "x\n")
                self.tearDown()
                self.setUp()

    def setUp_researcher_replay(self):
        (self.plugin / "roles/researcher.md").write_text("x\n")
        write_json(self.plugin / "tests/learning.json", {"gate:x": {
            "path": "roles/researcher.md", "cases": {
                "settled": {"prompt": "Requirements are settled", "expected": "READY"},
                "open": {"prompt": "A consequential decision is missing", "expected": "NEEDS-INFO"},
            },
        }})
        sh(self.plugin, "git", "add", "roles/researcher.md", "tests/learning.json")
        sh(self.plugin, "git", "commit", "-qm", "TEST: register planning cases")

    def test_researcher_without_matching_cases_stays_proposed(self):
        (self.plugin / "roles/researcher.md").write_text("x\n")
        sh(self.plugin, "git", "add", "roles/researcher.md")
        sh(self.plugin, "git", "commit", "-qm", "TEST: add researcher")
        self.propose("roles/researcher.md")
        self.assertEqual(self.advance_learning()["action"], "IDLE")
        self.assertEqual(E.all_runs(self.root)[-1]["outcome"], "proposed")

    def test_manual_learning_completion_leaves_build_tickets_open(self):
        self.next()
        self.agent_returns("learner", "VERDICT: NO-CHANGE\n\n## Human\nNo instruction needs a change.")
        self.assertEqual(E.next_action(self.root, learn_only=True)["action"], "IDLE")
        self.assertIsNone(E.state(self.root)["active"])
        self.assertIn("Status: open", self.ticket(1))

    def test_learning_leaves_a_concurrent_user_commit_intact(self):
        self.next()
        customer_note = self.plugin / "operator.md"
        customer_note.write_text("Keep this operator note.\n")
        sh(self.plugin, "git", "add", "operator.md")
        sh(self.plugin, "git", "commit", "-qm", "DOCS: record operator note")
        head = E.git(self.plugin, "rev-parse", "HEAD")

        self.agent_returns("learner", "VERDICT: NO-CHANGE\n\n## Human\nNo change.")
        act = self.next()
        self.assertEqual(act["action"], "STOP")
        self.assertIn("changed outside learner run", act["reason"])
        self.assertEqual(E.git(self.plugin, "rev-parse", "HEAD"), head)
        self.assertEqual(customer_note.read_text(), "Keep this operator note.\n")
        self.assertFalse((self.root / ".factory/learn.json").exists())

    def test_learning_leaves_a_switched_branch_intact(self):
        self.next()
        sh(self.plugin, "git", "checkout", "-qb", "operator")
        note = self.plugin / "operator.md"
        note.write_text("Work in progress.\n")
        self.agent_returns("learner", "VERDICT: NO-CHANGE\n\n## Human\nNo change.")
        self.assertEqual(self.next()["action"], "STOP")
        self.assertEqual(E.git(self.plugin, "branch", "--show-current"), "operator")
        self.assertEqual(note.read_text(), "Work in progress.\n")

    def test_learning_preserves_uncommitted_work_in_the_factory_checkout(self):
        self.next()
        note = self.plugin / "operator.md"
        note.write_text("Work in progress.\n")
        self.agent_returns("learner", "VERDICT: NO-CHANGE\n\n## Human\nNo change.")
        self.assertEqual(self.next()["action"], "STOP")
        self.assertEqual(note.read_text(), "Work in progress.\n")
        self.assertEqual(E.git(self.plugin, "stash", "list"), "")

    def test_invalid_candidate_cannot_write_live_tree(self):
        self.propose(path="other.md")
        self.assertEqual(self.advance_learning()["action"], "IDLE")
        self.assertFalse((self.plugin / "other.md").exists())
        self.assertEqual(read_json(self.root / ".factory/learn.json")["gate:x"]["tried"], ["r1", "r2"])


class InitScore(unittest.TestCase):
    def test_tools_gate_accepts_direct_script_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / ".factory/profile.json", {
                "repos": [], "conventions": {},
                "gates": [{"id": "backend:tools", "repo": "example-backend",
                           "cmd": "sh scripts/test-tools.sh", "requires": ["redis-server"],
                           "expect_tests": True}],
            })
            score = subprocess.run([sys.executable, str(Path(__file__).parent / "e2e/score_init.py"), str(root)],
                                   capture_output=True, text=True, check=True)
            self.assertIn("PASS  12 backend tool tests gated with redis-server or uv", score.stdout)


if __name__ == "__main__":
    unittest.main()

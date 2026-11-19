"""factory <command>. Every state change goes through here; agents never edit .factory/ themselves."""
import argparse
import json
import sys
from pathlib import Path

from . import detect as D
from . import engine as E
from . import evaluate as V
from . import hooks as H
from . import plans as A
from . import profile as P
from . import signals as S
from .util import FactoryError, find_root, write_json


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factory")
    ap.add_argument("--root", help="project root (default: the repo around the current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect", help="print what init can read without judgment (JSON)")
    v = sub.add_parser("verify", help="run setup and every gate, store baselines in the profile")
    v.add_argument("--gate", action="append", help="only these gate ids")
    v.add_argument("--no-setup", action="store_true")
    v.add_argument("--setup-only", action="store_true")
    n = sub.add_parser("next", help="advance the queue and print exactly one action (JSON)")
    choose = n.add_mutually_exclusive_group()
    choose.add_argument("--ticket", help="run this ticket (path or effort/NN) instead of the frontier")
    choose.add_argument("--learn-only", action="store_true", help="advance the active learner without starting other work")
    g = sub.add_parser("gate", help="run the gate for a run, wait up to 9 minutes")
    g.add_argument("run")
    w = sub.add_parser("wait", help="wait up to 9 minutes for the results of a run's started agents")
    w.add_argument("run")
    rl = sub.add_parser("release", help="human only: drop a started agent that will never deliver; it is started once more")
    rl.add_argument("run")
    rl.add_argument("stem")
    gr = sub.add_parser("gate-run", help=argparse.SUPPRESS)
    gr.add_argument("run")
    gr.add_argument("token", nargs="?", default="")
    r = sub.add_parser("record", help="store an agent result from stdin (fallback when the hook missed it)")
    r.add_argument("run")
    r.add_argument("stem")
    r.add_argument("spawn", type=int)
    sub.add_parser("status", help="recent runs")
    sub.add_parser("signals", help="learning signals and which are pending")
    q = sub.add_parser("queue", help="the frontier the factory will work through")
    board = sub.add_parser("board", help="show issue planning, delivery and review columns")
    board.add_argument("effort", nargs="?")
    board.add_argument("--json", action="store_true", help="return structured columns")
    approval = sub.add_parser("plan-review", help="approve finished issue Markdown in Plannotator")
    approval.add_argument("target", help="issue reference or effort directory")
    c = sub.add_parser("contract", help="print the current contract revision for an effort")
    c.add_argument("effort")
    ev = sub.add_parser("eval", help="record and triage observations about factory runs").add_subparsers(dest="eval")
    report = ev.add_parser("report", help="save a replayable observation")
    for field in ("summary", "observed", "expected", "check"):
        report.add_argument(f"--{field}", required=True)
    report.add_argument("--baseline", help="verified result; open a ticket in the configured feedback checkout")
    configure = ev.add_parser("configure", help="choose a separate initialized checkout for factory feedback")
    configure.add_argument("checkout")
    show = ev.add_parser("show", help="read a saved observation")
    show.add_argument("id")
    promote = ev.add_parser("ticket", help="open a task for a replayed observation")
    promote.add_argument("id")
    promote.add_argument("--checkout", required=True)
    promote.add_argument("--baseline", required=True)
    ln = sub.add_parser("learn", help="hand a lesson to the learner now (prints a SPAWN action)")
    ln.add_argument("--note", required=True)
    feature = sub.add_parser("feature-evidence", help="show the evidence for an implemented effort on the current checkout")
    feature.add_argument("effort")
    h = sub.add_parser("hook", help=argparse.SUPPRESS)
    h.add_argument("name", choices=["subagent-stop", "guard"])
    a = ap.parse_args(argv)

    if a.cmd == "hook":
        try:
            inp = json.load(sys.stdin)
            out = {"subagent-stop": H.subagent_stop, "guard": H.guard}[a.name](inp)
        except Exception as e:          # a broken hook must never block normal work
            print(f"factory hook {a.name}: {e}", file=sys.stderr)
            return 1
        if out:
            print(json.dumps(out))
        return 0

    root = find_root(a.root)
    try:
        if a.cmd == "detect":
            print(json.dumps(D.detect(root), indent=2))
        elif a.cmd == "verify":
            for res in P.verify(root, a.gate, setup=not a.no_setup, setup_only=a.setup_only):
                c = res.get("counts")
                print(f"{res['status']:7} {res['kind']:5} {res['id']:32} {res.get('seconds', '-')}s "
                      f"{('tests ' + str(c)) if c else ''} {res.get('reason') or ''}")
        elif a.cmd == "next":
            print(json.dumps(E.next_action(root, a.ticket, learn_only=a.learn_only), indent=2))
        elif a.cmd == "gate":
            print(E.gate(root, a.run))
        elif a.cmd == "wait":
            print(E.wait_agents(root, a.run))
        elif a.cmd == "release":
            E.release(root, a.run, a.stem)
            print(f"released {a.stem}")
        elif a.cmd == "gate-run":
            E.gate_run(root, a.run, a.token)
        elif a.cmd == "record":
            E.record(root, a.run, a.stem, a.spawn, sys.stdin.read())
            print(f"recorded {a.stem}")
        elif a.cmd == "status":
            active = E.state(root).get("active")
            print(f"active: {active or 'none'}\n" + E.status_lines(root))
        elif a.cmd == "signals":
            pending = {k for k, _ in S.pending_signals(root)}
            for key, items in sorted(S.collect(root).items()):
                print(f"{'PENDING ' if key in pending else '        '}{key:40} {len(items)} runs")
        elif a.cmd == "learn":
            with E.state_lock(root):
                if E.state(root).get("active") or E.pending_claims(root):
                    raise FactoryError("a run is active; finish it with /factory:run first")
                if E.dirty_paths(E.PLUGIN_ROOT):
                    raise FactoryError("the factory checkout has uncommitted changes; commit or stash them first")
                if not E.git(E.PLUGIN_ROOT, "rev-parse", "HEAD", check=False):
                    raise FactoryError("the factory repo needs a committed baseline before learning")
                print(json.dumps(E.start_learn(root, P.load(root), "user:note", {"runs": [], "digest": a.note}), indent=2))
        elif a.cmd == "queue":
            prof = P.load(root)
            cfg = E.tracker_cfg(prof)
            for t, _ in E.work_queue(root, cfg, *E.ticket_history(root, cfg)):
                print(f"{t.ref:40} {t.type:15} {t.title}")
        elif a.cmd == "board":
            columns = E.board(root, a.effort)
            if a.json:
                print(json.dumps(columns, indent=2))
            elif any(columns.values()):
                for title, rows in columns.items():
                    if not rows:
                        continue
                    print(f"## {title}\n")
                    for row in rows:
                        note = f" ({row['note']})" if row["note"] else ""
                        print(f"- [{row['ref']}](<{Path(root) / row['path']}>) {row['title']} [{row['status']}]{note}")
                    print()
            else:
                print("No issue plans.")
        elif a.cmd == "plan-review":
            print(json.dumps(A.review(root, a.target), indent=2))
        elif a.cmd == "feature-evidence":
            print(json.dumps(E.feature_evidence(root, a.effort), indent=2))
        elif a.cmd == "contract":
            if a.effort != Path(a.effort).name or a.effort in ("", ".", ".."):
                raise FactoryError("use the effort directory name")
            revision = E.T.contract_revision(root, E.tracker_cfg(P.load(root)), a.effort)
            if revision is None:
                raise FactoryError(f"no contract.md for {a.effort}")
            print(revision)
        elif a.cmd == "eval":
            if a.eval == "report":
                oid = V.report(root, a.summary, a.observed, a.expected, a.check)
                print(oid)
                if a.baseline is not None:
                    target = P.load(root).get("feedback_checkout")
                    if not target:
                        raise FactoryError("observation saved; configure a feedback checkout to open tickets from reports")
                    print(V.ticket(root, oid, target, a.baseline))
            elif a.eval == "configure":
                with E.state_lock(root):
                    if E.state(root).get("active") or E.pending_claims(root):
                        raise FactoryError("finish the active run before changing its profile")
                    target = V.development_checkout(a.checkout)
                    prof = P.load(root)
                    prof["feedback_checkout"] = str(target)
                    write_json(P.path(root), prof)
                print(target)
            elif a.eval == "show":
                print(json.dumps(V.load(root, a.id), indent=2))
            elif a.eval == "ticket":
                print(V.ticket(root, a.id, a.checkout, a.baseline))
            else:
                for path in sorted(V.observations(root).glob("*.json")):
                    print(f"{path.stem}  {V.load(root, path.stem)['summary']}")
    except FactoryError as e:
        print(f"factory: {e}", file=sys.stderr)
        return 2
    return 0

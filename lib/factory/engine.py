"""The run state machine. `next_action` returns exactly one action; the orchestrator only executes it.

Ticket run stages: research -> build -> gate -> review -> (delivered | needs-info | needs-human).
Learn runs: learn -> done. One run is active at a time; `.factory/state.json` names it.
"""
import datetime
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from . import gates as G
from . import profile as P
from . import signals as S
from . import stack as K
from . import tracker as T
from .hooks import READ_ONLY
from .util import (FACTORY_BIN, PLUGIN_ROOT, FactoryError, atomic_write_text, dirty_paths, factory_dir, factory_sha, git, git_ok,
                   now, read_json, write_json)

ROLES = PLUGIN_ROOT / "roles"
MODELS = {"researcher": "opus", "builder": "opus", "reviewer": "opus", "security": "claude-mythos-5-2",
          "ui-tester": "sonnet", "learner": "opus"}
AGENT_MODELS = {"sonnet", "opus", "haiku", "fable"}   # the Agent tool takes only these; other ids: the agent file decides
DIFFICULTY_MODELS = {"simple": "sonnet", "medium": "opus", "extreme": "fable"}   # builder and reviewer, from the brief
UI_SKILL = "emil-design-eng"   # every build round that changes ui_paths files must load it
MAX_GATE_FAILS = 2       # red gates sent back to the builder before a human is asked
MAX_REVIEW_ROUNDS = 3
AGENT_IDLE_MIN = 60      # a started agent is stuck once no factory agent has used a tool for this long
STATUS_DEFAULTS = {"queue": ["open", "ready-for-agent"], "claimed": "claimed", "needs_info": "needs-info",
                   "plan_review": "needs-plan-review", "plan_changes": "plan-changes",
                   "needs_human": "needs-human", "ready": "ready-for-review",
                   "parked": "ready-for-human", "done": ["resolved", "done", "delivered", "wontfix", "superseded", "declined"]}
FINDING = re.compile(r"^\s*-\s*\[(blocker|required|nit)\]\s*([\w-]+)?", re.I | re.M)
VALID_VERDICTS = {"reviewer": {"PASS", "CHANGES"}, "security": {"PASS", "CHANGES"},
                  "ui-tester": {"PASS", "CHANGES", "BLOCKED"}}
REVIEW_ROLES = {"review": "reviewer", "security": "security", "ui": "ui-tester"}


# ---- storage ------------------------------------------------------------------------------------

def runs_dir(root):
    return factory_dir(root) / "runs"


def archive_dirs(root):
    profile = read_json(P.path(root)) or {}
    tracker = profile.get("tracker", {}).get("root")
    return (Path(root) / tracker).glob("*/runs") if tracker else ()


def run_dir(root, rid):
    if Path(rid).name != rid or rid in ("", ".", ".."):
        raise FactoryError(f"invalid run ID {rid!r}")
    local = runs_dir(root) / rid
    if (local / "run.json").is_file():
        return local
    return next((d / rid for d in archive_dirs(root) if (d / rid / "run.json").is_file()), local)


def allocate_run_id(root, suffix):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S%f")
    suffix = re.sub(r"[^\w-]+", "-", suffix)
    rid = f"{stamp}-{suffix}"
    attempt = 1
    while True:
        try:
            local = runs_dir(root) / rid
            if run_dir(root, rid) != local:
                raise FileExistsError(rid)
            local.mkdir(parents=True)
        except FileExistsError:
            attempt += 1
            rid = f"{stamp}-{suffix}-{attempt:04d}"
        else:
            return rid


def state(root):
    return read_json(factory_dir(root) / "state.json", {"active": None})


@contextmanager
def state_lock(root, *, wait=True):
    """Serialize transitions on a local checkout without adding a state file."""
    try:
        fd = os.open(factory_dir(root), os.O_RDONLY)
    except FileNotFoundError as e:
        raise FactoryError("No .factory/profile.json. Run /factory:init first.") from e
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if wait:
                raise
            yield False
        else:
            yield True
    finally:
        os.close(fd)


def set_active(root, rid):
    write_json(factory_dir(root) / "state.json", {"active": rid})


def load_run(root, rid):
    run = read_json(run_dir(root, rid) / "run.json")
    if run is None:
        raise FactoryError(f"unknown run {rid}")
    return run


def save_run(root, run):
    write_json(runs_dir(root) / run["id"] / "run.json", run)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _file_sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def _json_or_none(path):
    try:
        return read_json(path)
    except ValueError:
        return None


def store_result(root, rid, stem, spawn, text, via, **extra):
    """Write one spawn's result and, last, its proof, so a proof always points at a complete result."""
    d = runs_dir(root) / rid
    atomic_write_text(d / f"{stem}@{spawn}.md", text)
    atomic_write_text(d / f"{stem}@{spawn}.prov.json",
                      json.dumps({"spawn": spawn, "sha256": _sha(text), "via": via, **extra}))


def result_path(root, run, stem):
    """The current spawn's result file when its proof matches it; anything else counts as missing."""
    n = run.get("spawn_ids", {}).get(stem)
    if n is None:
        return None
    d = run_dir(root, run["id"])
    md, proof = d / f"{stem}@{n}.md", _json_or_none(d / f"{stem}@{n}.prov.json")
    if not isinstance(proof, dict) or proof.get("spawn") != n or not md.exists() or _sha(md.read_text()) != proof.get("sha256"):
        return None
    return md


def result(root, run, stem):
    p = result_path(root, run, stem)
    return p.read_text() if p else None


def event(run, kind, **detail):
    run["events"].append({"t": now(), "stage": run["stage"], "event": kind, **detail})


def verdict(text):
    m = re.match(r"\s*VERDICT:\s*([A-Za-z-]+)", text or "")
    return m.group(1).upper() if m else None


def section(text, name):
    m = re.search(rf"^##\s*{re.escape(name)}\s*$(.*?)(?=^##\s|\Z)", text or "", re.M | re.S | re.I)
    return m.group(1).strip() if m else ""


def archive_path(root, prof, run):
    effort = run.get("effort") or run["ticket_ref"].rsplit("/", 1)[0]
    return Path(root) / prof["tracker"]["root"] / effort / "runs" / run["id"]


def archive_screenshots(dest, stem, text):
    screenshots = {}
    paths = re.findall(r"(?m)^-\s+`?(/tmp/factory-ui-[\w-]+/[\w.-]+\.(?:png|jpe?g|webp))`?\s*:",
                       section(text, "Screenshots"))
    for path in paths:
        source = Path(path)
        if source.parent.is_symlink() or source.is_symlink() or not source.is_file():
            continue
        relative = Path("screenshots") / stem / source.name
        if relative.as_posix() in screenshots.values():
            relative = relative.with_name(f"{source.stem}-{_sha(path)[:12]}{source.suffix}")
        (dest / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest / relative)
        screenshots[path] = relative.as_posix()
    return screenshots


def archive_run(root, prof, run):
    source = runs_dir(root) / run["id"]
    if not source.exists():
        return
    dest = archive_path(root, prof, run)
    if source.is_symlink() or dest.resolve() != dest.absolute() or not dest.resolve().is_relative_to(Path(root).resolve()):
        raise OSError(f"invalid archive path {dest}")
    if dest.exists():
        prior = _json_or_none(dest / "run.json") or {}
        if (prior.get("id"), prior.get("ticket"), prior.get("ended")) != (run["id"], run["ticket"], run["ended"]):
            raise OSError(f"archive already exists at {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Publish a complete archive before removing the working copy, so an interrupted copy can be retried.
        with tempfile.TemporaryDirectory(prefix=".archive-", dir=dest.parent) as staging:
            bundle = Path(staging) / "bundle"
            bundle.mkdir()
            metadata = {k: v for k, v in run.items() if k not in ("fingerprint", "outside_repos", "round_heads", "feedback")}
            screenshots = {}
            for stem in run.get("spawn_ids", {}):
                path = result_path(root, run, stem)
                if path:
                    shutil.copyfile(path, bundle / path.name)
                    proof = path.with_suffix(".prov.json")
                    shutil.copyfile(proof, bundle / proof.name)
                    if stem.startswith("ui-"):
                        captures = run.get("ui_captures", {}).get(stem)
                        if captures is None:
                            captures = archive_screenshots(bundle, stem, path.read_text())
                        else:
                            for rel in captures.values():
                                (bundle / rel).parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(source / rel, bundle / rel)
                        screenshots.update(captures)
            for path in (source / "pr.md", *source.glob("feedback-*.md")):
                if path.is_file():
                    shutil.copyfile(path, bundle / path.name)
            metadata["gate_sha"] = {}
            for round_no, digest in run.get("gate_sha", {}).items():
                path = source / f"gate-{round_no}.json"
                if _file_sha(path) != digest:
                    continue
                gate = read_json(path)
                for report in gate["results"]:
                    report.pop("log", None)
                    tail = report.pop("tail", "")
                    if report["status"] == "fail" and tail:
                        report["tail"] = tail[-1500:]
                write_json(bundle / path.name, gate)
                metadata["gate_sha"][round_no] = _file_sha(bundle / path.name)
            if screenshots:
                metadata["screenshots"] = screenshots
                pr = bundle / "pr.md"
                if pr.is_file():
                    with pr.open("a") as out:
                        out.write("\n## Screenshots\n" +
                                  "".join(f"- [{Path(p).name}]({p})\n" for p in screenshots.values()))
            write_json(bundle / "run.json", metadata)
            bundle.rename(dest)
    shutil.rmtree(source)


def line_field(text, key):
    m = re.search(rf"^\**{key}\**:\s*(.+)$", text or "", re.M | re.I)
    return m.group(1).strip().strip("`") if m else ""


def tracker_cfg(prof):
    cfg = dict(prof["tracker"])
    cfg["status"] = {**STATUS_DEFAULTS, **cfg.get("status", {})}
    cfg.setdefault("build_types", ["implementation", "task"])
    return cfg


# ---- actions ------------------------------------------------------------------------------------

def factory_command(*args):
    return shlex.join([str(FACTORY_BIN), *map(str, args)])


def spawn(root, prof, run, roles_and_stems, context, extra="", *, instructions=None):
    """Write one prompt file per agent (role text read fresh from disk) and return a SPAWN action. Every spawn gets
    its own number; only a result proven for that number counts. A phase of read-only agents is fingerprinted."""
    agents = []
    tier = DIFFICULTY_MODELS.get(run.get("difficulty"))
    models = {**MODELS, **({"builder": tier, "reviewer": tier} if tier else {}), **(prof.get("models") or {})}
    for role, stem in roles_and_stems:
        n = run["spawn_seq"] = run.get("spawn_seq", 0) + 1
        run.setdefault("spawn_ids", {})[stem] = n
        prompt_file = runs_dir(root) / run["id"] / "prompts" / f"{stem}.md"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        role_text = instructions if instructions is not None else (ROLES / f"{role}.md").read_text()
        skill = ui_handoff(root, prof, run) if role == "builder" and run["type"] == "ticket" else None
        handoff = "\n# Attached UI design skill\n\n" + skill if skill else ""
        prompt_file.write_text(role_text + "\n\n# Run context\n\n" + context(role, stem) + extra + handoff)
        if skill:
            run.setdefault("ui_prompt_proof", {})[stem] = {"spawn": n, "digest": _file_sha(prompt_file)}
        run["pending"][f"factory:{role}"] = stem
        agent = {
            "subagent_type": f"factory:{role}", "model": models[role],
            "description": f"{role} {run.get('ticket_ref', run['id'])} ({stem} #{n})",
            "prompt": f"FACTORY RUN {run['id']} RESULT {stem} SPAWN {n}\nRead the prompt at {str(prompt_file)!r} and follow it exactly. "
                      f"Your final message must start with the VERDICT line defined there."}
        if agent["model"] not in AGENT_MODELS:
            del agent["model"]      # e.g. Mythos: the Agent tool refuses the id, the agent file's model applies
        agents.append(agent)
        event(run, "spawn", role=role, stem=stem, spawn=n)
    stems = [s for _, s in roles_and_stems]
    if run["type"] == "learn" or not all(role in READ_ONLY for role, _ in roles_and_stems):
        run.pop("fingerprint", None)
    elif not set(stems) <= set((run.get("fingerprint") or {}).get("skip", [])):
        run["fingerprint"] = {"skip": stems, "state": fingerprint(root, prof, run, stems)}
    # else: a respawn inside a running read-only phase keeps the phase's fingerprint
    return {"action": "SPAWN", "run": run["id"], "agents": agents}


# ---- read-only phases ------------------------------------------------------------------------------
# Agents run with the user's shell, so read-only roles are checked, not sandboxed: what they must leave untouched
# is fingerprinted when they start and compared when their results are used. This detects a mistaken or
# shortcut-taking agent; one that rewrites both the workspace and run.json consistently is not detected.

def _repo_state(path, skip_prefixes=()):
    files = {rel: _file_sha(Path(path) / rel) for rel in dirty_paths(path, skip_prefixes, check=False)}
    return {"branch": git(path, "branch", "--show-current", check=False),
            "head": git(path, "rev-parse", "--verify", "--quiet", "HEAD", check=False) or "none", "files": files}


def repo_checkout(root, prof):
    skip = (".factory/", prof["tracker"]["root"].rstrip("/") + "/")
    return {r["path"]: _repo_state(Path(root) / r["path"], skip if r["path"] == "." else ())
            for r in prof["repos"]}


def fingerprint(root, prof, run, skip_stems):
    """Every profile repo and the factory (branch, HEAD, content of each changed or untracked file), the run's own
    ticket, and .factory except what the hook and the engine write while the phase runs. Other tickets are left
    out: the human answers and rejects tickets while the queue runs."""
    out = {f"repo {name}": snapshot for name, snapshot in repo_checkout(root, prof).items()}
    out["factory plugin"] = _repo_state(PLUGIN_ROOT)
    out["ticket"] = {run["ticket"]: _file_sha(Path(root) / run["ticket"])} if run.get("ticket") else {}
    out["archived evidence"] = {str(p.relative_to(root)): _file_sha(p)
                                for directory in archive_dirs(root) for p in directory.glob("*/*")
                                if p.suffix in (".json", ".md") and p.is_file()}
    fd, own = factory_dir(root), f"runs/{run['id']}/"
    fac = {}
    for p in sorted(fd.rglob("*")) if fd.is_dir() else []:
        rel = str(p.relative_to(fd))
        if not p.is_file() or rel in ("hooks.log", "hooks.log.1", "beat", own + "run.json") or rel.endswith(".tmp") or \
                rel.startswith("evaluations/") or \
                any(rel.startswith(f"{own}{s}@") or rel == f"{own}prompts/{s}.md" for s in skip_stems):
            continue
        fac[rel] = _file_sha(p)
    out[".factory"] = fac
    return out


def workspace_changes(root, prof, run):
    fp = run.get("fingerprint")
    if not fp:
        return []
    now_state = json.loads(json.dumps(fingerprint(root, prof, run, fp["skip"])))
    out = []
    for key, before in fp["state"].items():
        after = now_state.get(key)
        if after == before:
            continue
        if isinstance(before, dict) and "files" in before:
            what = [k for k in ("branch", "head") if before[k] != after[k]]
            before, after = before["files"], after["files"]
        else:
            what = []
        what += sorted(f for f in {*before, *after} if before.get(f) != after.get(f))
        out.append(f"{key}: {', '.join(what[:5])}")
    return out


def tampered(root, prof, run, who):
    """Finish the run when the workspace changed while read-only agents ran."""
    changes = workspace_changes(root, prof, run)
    run.pop("fingerprint", None)
    if changes:
        finish(run, "needs-human", f"The workspace changed while the {who} ran, although it is "
                                                f"read-only: " + "; ".join(changes)[:800])
    return bool(changes)


def start_gate(root, run):
    """A fresh gate per round: drop any report written before the runner starts and expect this round's token."""
    n = str(run["rounds"]["build"])
    for suffix in (".json", ".lock"):
        (runs_dir(root) / run["id"] / f"gate-{n}{suffix}").unlink(missing_ok=True)
    run.get("gate_sha", {}).pop(n, None)
    run.setdefault("gate_token", {})[n] = secrets.token_hex(16)
    return gate_action(run)


def gate_action(run):
    return {"action": "RUN", "run": run["id"], "cmd": factory_command("gate", run["id"]), "timeout_ms": 600000,
            "note": "Blocks up to 9 minutes. If it prints RUNNING, run it again."}


def finish(run, outcome, reason=""):
    run["stage"], run["outcome"], run["ended"] = outcome, outcome, now()
    event(run, "finish", outcome=outcome, reason=reason[:500])
    run["finish_reason"] = reason
    run["pending"] = {}


def finalize_ticket(root, cfg, run):
    ticket = Path(root) / run["ticket"]
    if "finish_reason" not in run or "before_claim" in run or not ticket.is_file():
        return
    statuses = cfg["status"]
    new = {"needs-info": statuses["needs_info"], "needs-human": statuses["needs_human"],
           "delivered": statuses["ready"]}[run["outcome"]]
    text = ticket.read_text()
    if T.first_word(T.header(text, "Status")) == statuses["claimed"]:
        T.set_status(root, run["ticket"], new)
    marker = f"Factory run `{run['id']}`."
    if run["finish_reason"] and marker not in text:
        T.comment(root, run["ticket"], f"{run['finish_reason']}\n\n{marker}")


# ---- ticket runs --------------------------------------------------------------------------------

def preflight(root, prof):
    """Check the repos before switching them for a ticket."""
    tracker_root = prof["tracker"]["root"]
    for repo in prof["repos"]:
        path = Path(root) / repo["path"]
        dirty = dirty_paths(path, (tracker_root, ".factory") if repo["path"] == "." else ())
        if dirty:
            return f"{repo['path']} has uncommitted changes ({', '.join(dirty[:5])}); the factory works in this checkout"
        if not git_ok(path, "rev-parse", "--verify", repo["base"]):
            return f"{repo['path']}: base {repo['base']} does not exist"
        signing = signing_problem(path)
        if signing:
            return f"{repo['path']}: {signing}"
    missing = sorted({m for g in prof["gates"] if g.get("tier", "fast") == "fast"
                      for m in G.missing_requirements(g.get("requires"))})
    if missing:
        return "fast gates need: " + ", ".join(missing)
    return None


def check_gate_inputs(root, prof):
    stale = P.drift(root, prof)
    if stale:
        verify = factory_command("verify", "--no-setup", "--gate")
        raise FactoryError(f"gate inputs changed since these gates were verified: {', '.join(stale)}. "
                           f"Run `{verify} <id>` on the ticket's base checkout.")


def signing_problem(repo):
    """Commits would fail: ssh signing is on but no agent can sign (a literal public key needs one, unless
    gpg.ssh.program names its own signer, such as 1Password's op-ssh-sign, which needs no SSH_AUTH_SOCK)."""
    cfg = lambda k: git(repo, "config", "--get", k, check=False)
    if cfg("commit.gpgsign") != "true" or cfg("gpg.format") != "ssh":
        return None
    if cfg("user.signingkey").startswith("ssh-") and not cfg("gpg.ssh.program") and not os.environ.get("SSH_AUTH_SOCK"):
        return "commit signing uses an ssh key from the agent, but no ssh-agent is reachable (SSH_AUTH_SOCK unset)"
    return None


def research_checkout(root, prof, stack_bases):
    """Use one pinned revision per repo before the researcher reads any files."""
    heads, switches = {}, []
    for repo in prof["repos"]:
        name = repo["path"]
        path = Path(root) / name
        ref = stack_bases.get(name, {}).get("head") or repo["base"]
        head = heads[name] = git(path, "rev-parse", "--verify", f"{ref}^{{commit}}")
        current = git(path, "rev-parse", "HEAD")
        if current == head:
            continue
        if name == "." and git(path, "diff", "--name-only", current, head, "--",
                               prof["tracker"]["root"], ".factory/profile.json"):
            raise FactoryError(f"research base {ref} changes the tracker or factory profile in {name}")
        branch = git(path, "branch", "--show-current")
        restore = ("switch", branch) if branch else ("switch", "--detach", current)
        switches.append((path, head, restore))
    changed = []
    try:
        for path, head, restore in switches:
            git(path, "switch", "--detach", head)
            changed.append((path, restore))
        check_gate_inputs(root, prof)
    except FactoryError as e:
        failures = [str(path) for path, restore in reversed(changed) if not git_ok(path, *restore)]
        if failures:
            raise FactoryError(f"{e}. Could not restore checkout: {', '.join(failures)}") from e
        raise
    return heads


def new_run(root, prof, ticket, stack):
    cfg = tracker_cfg(prof)
    source = (Path(root) / ticket.path).read_bytes().decode("utf-8")
    before_claim = _sha(source)
    if before_claim != ticket.revision:
        raise FactoryError(f"The ticket changed while preparing its run: {ticket.path}.")
    history = [r for r in all_runs(root) if r.get("ticket") == ticket.path]
    prev = [r for r in history if r.get("outcome") == "delivered"]
    feedback = T.human_comments_since_factory(root, ticket.path)
    prior_stack = prev[-1].get("stacked_on", {}) if prev else {}
    same_stack = prior_stack == stack["stacked_on"]
    if prior_stack and not same_stack and stack["stacked_on"].items() <= prior_stack.items():
        tickets, latest = ticket_history(root, cfg)
        same_stack = K.rejected_base(prev[-1], tickets, latest, cfg["status"]) is None
    reopen = prev and feedback and prev[-1].get("contract") == ticket.contract and same_stack
    if reopen:
        check_gate_inputs(root, prof)
    research_bases = {} if reopen else research_checkout(root, prof, stack["stack_bases"])
    rid = allocate_run_id(root, f"{ticket.number}-{ticket.effort[:24]}")
    run = {"id": rid, "type": "ticket", "ticket": ticket.path, "ticket_ref": ticket.ref, "title": ticket.title,
           "effort": ticket.effort, "contract": ticket.contract, "research_bases": research_bases,
           "stage": "research", "rounds": {"build": 0, "gate_fail": 0, "review": 0}, "pending": {},
           "repos": [], "branch": None, "base": {}, "profile_sha": P.sha(root), "factory_sha": factory_sha(),
           "started": now(), "ended": None, "outcome": None, "events": [], **stack}
    if reopen:
        last = prev[-1]
        run.update(stage="build", repos=last["repos"], branch=last["branch"], base=last["base"],
                   reopened_from=last["id"], difficulty=last.get("difficulty"),
                   stacked_on=prior_stack, stack_bases=last.get("stack_bases", {}))
        run["spawn_ids"] = {"research": 0}
        store_result(root, rid, "research", 0, result(root, last, "research") or "", "inherited", **{"from": last["id"]})
        write_feedback(root, run, "Your earlier delivery was rejected by the human. Their comments:\n\n" + "\n".join(feedback))
        for name in run["repos"]:
            git(Path(root) / name, "switch", run["branch"])
        event(run, "reopened", feedback=feedback)
    elif history and history[-1].get("outcome") == "needs-info" and history[-1].get("contract") == ticket.contract:
        brief = result_path(root, history[-1], "research")
        if brief:
            run["previous_brief"] = str(brief)
    # Store enough to recognize the claim even if the process dies just after writing the ticket.
    run["before_claim"] = before_claim
    run["ticket_sha"] = _sha(T.status_text(source, cfg["status"]["claimed"]))
    run["claim_checkout"] = repo_checkout(root, prof)
    save_run(root, run)
    return run


def pending_claims(root):
    claims = []
    for p in runs_dir(root).glob("*/run.json"):
        run = _json_or_none(p)
        if run and "before_claim" in run and not run.get("ended"):
            claims.append(run["id"])
    return sorted(claims)


def complete_claim(root, prof, cfg, run):
    ticket = run["ticket"]
    path = Path(root) / ticket
    if P.sha(root) != run["profile_sha"]:
        reason = f"The factory profile changed before claiming {ticket}."
    elif T.contract_revision(root, cfg, run["effort"]) != run["contract"]:
        reason = f"The feature contract changed before claiming {ticket}."
    elif repo_checkout(root, prof) != run["claim_checkout"]:
        reason = f"The checkout changed before claiming {ticket}."
    else:
        revision = _file_sha(path)
        if revision == run["before_claim"]:
            T.set_status(root, ticket, cfg["status"]["claimed"], expected=revision)
            revision = _file_sha(path)
        if revision == run["ticket_sha"]:
            run.pop("before_claim")
            run.pop("claim_checkout")
            if changed_contract(root, prof, run):
                return {"action": "STOP", "reason": run["finish_reason"]}
            return None
        reason = f"The ticket changed before the factory could confirm its claim: {ticket}."
    finish(run, "needs-human", reason)
    return {"action": "STOP", "reason": reason}


def write_feedback(root, run, text):
    n = run["rounds"]["build"] + 1
    p = runs_dir(root) / run["id"] / f"feedback-{n}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    run["feedback"] = str(p)


def context_for(root, prof, run):
    rdir = runs_dir(root) / run["id"]
    repo_lines = "\n".join(f"- `{r['path']}` (base `{r['base']}`)" for r in prof["repos"])
    conv = prof["conventions"]

    def ctx(role, stem):
        lines = [f"- Repository root: `{root}`", f"- Ticket: `{run['ticket']}` ({run.get('ticket_ref')})",
                 "- Result: the factory stores your final message itself; never write it to a file."]
        if role == "researcher":
            lines += [f"- Repos you may plan for:\n{repo_lines}",
                      f"- Branch name must match `{conv.get('branch_regex', '.*')}` and be one kebab-case name used in every touched repo."]
            if run.get("previous_brief"):
                lines.append(f"- Prior research: `{run['previous_brief']}`. Start with the new ticket comments. "
                             "Reuse prior evidence after checking what the answers or intervening code changes affect.")
            if run.get("stack_bases"):
                lines.extend(f"- Stacked research base in `{name}`: `{base['branch']}` at `{base['head']}`."
                             for name, base in run["stack_bases"].items())
        if run.get("contract"):
            contract = Path(root) / prof["tracker"]["root"] / run["effort"] / "contract.md"
            lines.append(f"- Feature contract: `{contract}` (revision `{run['contract']}`).")
        if role in ("builder", "reviewer", "security", "ui-tester"):
            lines += [f"- Brief: `{result_path(root, run, 'research')}`", f"- Branch: `{run['branch']}`",
                      "- Repos and bases:\n" + "\n".join(f"  - `{n}` from `{run['base'][n]}`" for n in run["repos"])]
        if role == "builder":
            fast = [g for g in prof["gates"] if g["repo"] in run["repos"] and g.get("tier", "fast") == "fast"]
            lines += [f"- Round: {run['rounds']['build']}",
                      f"- Commit subjects must match `{conv.get('commit_regex', '.*')}`.",
                      "- Gates the factory will run (run the fast ones yourself first, exit code not piped):\n" +
                      "\n".join(f"  - `{g['repo']}`: `{g['cmd']}`" for g in fast)]
            if run.get("feedback"):
                lines.append(f"- Feedback to address this round: `{run['feedback']}`")
        if role in ("reviewer", "security", "ui-tester"):
            gate = latest_gate(root, run)
            if gate:
                lines.append(f"- Gate evidence: `{gate}`")
            if run.get("reviewed_heads"):
                lines.append("- Tested commits:\n" + "\n".join(
                    f"  - `{n}` at `{sha}`" for n, sha in run["reviewed_heads"].items()))
            if run["rounds"]["review"] > 1 and run.get("review_base_heads"):
                lines.append("- Round " + str(run["rounds"]["review"]) + ": review only the commits since " +
                             ", ".join(f"`{n}`@`{s}`" for n, s in run["review_base_heads"].items()) +
                             f", and whether the findings in `{rdir}` review files of earlier rounds were fixed.")
        if prof.get("rules"):
            lines.append("- Project rules not written elsewhere:\n" + "\n".join(f"  - {r}" for r in prof["rules"]))
        return "\n".join(lines) + "\n"
    return ctx


def latest_gate(root, run):
    files = sorted(run_dir(root, run["id"]).glob("gate-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return files[-1] if files else None


def overdue(root, run, stem):
    """No time limit while agents work: the guard hook touches .factory/beat on every factory agent tool call."""
    started = [e["t"] for e in run["events"] if e["event"] == "spawn" and e.get("stem") == stem]
    if not started:
        return True
    last = datetime.datetime.fromisoformat(started[-1]).timestamp()
    beat = factory_dir(root) / "beat"
    if beat.exists():
        last = max(last, beat.stat().st_mtime)
    return time.time() - last > AGENT_IDLE_MIN * 60


def wait_action(run):
    return {"action": "RUN", "run": run["id"], "cmd": factory_command("wait", run["id"]), "timeout_ms": 600000,
            "note": "Agents of this run are still working. Blocks up to 9 minutes. If it prints RUNNING, run it again."}


def respawn_or_fail(root, prof, run, role, stem):
    """A started agent is awaited, never replaced: wait while factory agents keep using tools, then ask the orchestrator to record its
    result, then stop. A result that was never started (a reopened ticket) is spawned once, then a human decides."""
    if stem in run["pending"].values():
        if not overdue(root, run, stem):
            return wait_action(run)
        if not run.get(f"asked:{stem}"):
            run[f"asked:{stem}"] = True
            n = run.get("spawn_ids", {}).get(stem)
            return {"action": "RECORD", "run": run["id"], "stem": stem, "spawn": n,
                    "cmd": factory_command("record", run["id"], stem, n),
                    "note": "The hook did not capture this result. Pipe the agent's complete final message into the "
                            "command with a quoted heredoc, then call next. If the agent returned nothing, call next."}
        release = factory_command("release", run["id"], stem)
        return {"action": "STOP", "reason": f"The {role} ({stem}) of run {run['id']} has delivered no result, and no factory agent "
                f"has used a tool for {AGENT_IDLE_MIN} minutes. If it is still running, let it finish, then start /factory:run again. If it "
                f"is gone, run `{release}`, then /factory:run starts it once more."}
    key = f"respawn:{stem}"
    if not run.get(key):
        run[key] = True
        event(run, "missing-result", stem=stem)
        return spawn(root, prof, run, [(role, stem)], context_for(root, prof, run))
    finish(run, "needs-human", f"The {role} returned no usable result twice (stage {run['stage']}).")
    return None


def spawn_builder(root, prof, run):
    run["rounds"]["build"] += 1
    run["stage"] = "build"
    run["outside_repos"] = {r["path"]: _repo_state(Path(root) / r["path"], (".factory/",))
                            for r in prof["repos"] if r["path"] not in run["repos"]}
    run["round_heads"] = {name: git(Path(root) / name, "rev-parse", run["branch"]) for name in run["repos"]}
    return spawn(root, prof, run, [("builder", f"build-{run['rounds']['build']}")], context_for(root, prof, run))


def round_files(root, run):
    """Files the current build round committed, prefixed with their repo."""
    return [f"{name}/{f}" if name != "." else f for name, start in run.get("round_heads", {}).items()
            for f in git(Path(root) / name, "diff", "--name-only", f"{start}..{run['branch']}").splitlines()]


def ui_handoff(root, prof, run):
    path = (prof.get("review") or {}).get("ui_skill_file")
    if not isinstance(path, str) or not path:
        return None
    brief = result(root, run, "research")
    if line_field(brief, "UI").lower() != "yes" and run.get("ui_skill_round") != run["rounds"]["build"]:
        globs = prof["review"].get("ui_paths", [])
        if not globs or run["rounds"]["build"] == 1 or not any(
                G.fnmatch.fnmatch(f"{repo}/{path}" if repo != "." else path, pattern)
                for repo in run["repos"] for path in G.changed_files(root, run, repo) for pattern in globs):
            return None
    try:
        skill = Path(path).expanduser().read_text()
    except (OSError, LookupError, ValueError):
        return None
    header = skill.split("---", 2)
    return skill if len(header) == 3 and not header[0] and line_field(header[1], "name") == UI_SKILL else None


def loaded_skills(root, run, stem):
    """Skills the agent of this spawn loaded, read from its transcript; None when its result has no transcript."""
    proof = _json_or_none(runs_dir(root) / run["id"] / f"{stem}@{run['spawn_ids'][stem]}.prov.json") or {}
    try:
        lines = Path(proof["transcript"]).read_text().splitlines()
    except (KeyError, TypeError, OSError):
        return None
    out = set()
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
                out.add(str((block.get("input") or {}).get("skill", "")).split(":")[-1])
    return out


def ui_skill_problem(root, prof, run, stem):
    """Why this build round broke the UI rule (load UI_SKILL whenever the round changes UI files), or None."""
    pats = prof.get("review", {}).get("ui_paths", [])
    ui = [f for f in round_files(root, run) if any(G.fnmatch.fnmatch(f, p) for p in pats)]
    if not ui and run.get("ui_skill_round") != run["rounds"]["build"]:
        return None
    prompt = runs_dir(root) / run["id"] / "prompts" / f"{stem}.md"
    proof = run.get("ui_prompt_proof", {}).get(stem)
    if (proof and proof == {"spawn": run["spawn_ids"][stem], "digest": _file_sha(prompt)}
            and prompt.is_file() and line_field(result(root, run, stem), "UI-Skill-SHA256") == proof["digest"]):
        return None
    skills = loaded_skills(root, run, stem)
    if skills is None:
        return f"Whether the builder loaded the `{UI_SKILL}` skill cannot be verified: its result has no transcript."
    if UI_SKILL in skills:
        return None
    return (f"The builder changed UI files ({', '.join(ui[:5]) or 'in the round before'}) without loading the "
            f"`{UI_SKILL}` skill.")


def spawn_reviewers(root, prof, run, checkout):
    run["rounds"]["review"] += 1
    n = run["rounds"]["review"]
    files = [f for name in run["repos"] for f in (f"{name}/{p}" if name != "." else p
                                                  for p in G.changed_files(root, run, name, checkout[name]["head"]))]
    review = prof.get("review", {})
    roles = [("reviewer", f"review-{n}")]
    if any(G.fnmatch.fnmatch(f, pat) for f in files for pat in review.get("security_paths", [])):
        roles.append(("security", f"security-{n}"))
    if any(G.fnmatch.fnmatch(f, pat) for f in files for pat in review.get("ui_paths", [])):
        roles.append(("ui-tester", f"ui-{n}"))      # every round: a backend-only fix can still break the screen
    run["stage"], run["review_stems"] = "review", [s for _, s in roles]
    run["review_base_heads"] = run.get("reviewed_heads", {})
    run["reviewed_heads"] = {name: checkout[name]["head"] for name in run["repos"]}
    return spawn(root, prof, run, roles, context_for(root, prof, run))


def advance(root, prof, run):
    """Return the next action for this run, or None when it reached an end state."""
    stage = run["stage"]
    if stage == "research":
        text = result(root, run, "research")
        if text is None:
            if not any(e["event"] == "spawn" for e in run["events"]):
                return spawn(root, prof, run, [("researcher", "research")], context_for(root, prof, run))
            return respawn_or_fail(root, prof, run, "researcher", "research")
        if tampered(root, prof, run, "researcher"):
            return None
        if changed_contract(root, prof, run):
            return None
        v = verdict(text)
        if v == "NEEDS-INFO":
            finish(run, "needs-info", "Questions before this can be built:\n" + section(text, "Questions"))
            return None
        if v != "READY":
            finish(run, "needs-human", f"Research ended with verdict {v}.")
            return None
        return start_build(root, prof, run, text)
    if stage == "build":
        stem = f"build-{run['rounds']['build']}"
        text = result(root, run, stem)
        if text is None:
            return respawn_or_fail(root, prof, run, "builder", stem)
        if changed_contract(root, prof, run):
            return None
        v = verdict(text)
        if v == "DONE":
            outside = [name for name, before in run.get("outside_repos", {}).items()
                       if _repo_state(Path(root) / name, (".factory/",)) != before]
            if outside:
                finish(run, "needs-human", "Builder changed repos outside declared repos: " + ", ".join(outside))
                return None
            problem = ui_skill_problem(root, prof, run, stem)
            if problem:
                if run.get("ui_skill_round") == run["rounds"]["build"]:
                    finish(run, "needs-human", problem + " A reminder round did not change that.")
                    return None
                run["ui_skill_round"] = run["rounds"]["build"] + 1
                event(run, "ui-skill-missing", stem=stem)
                write_feedback(root, run, problem + f"\n\nFollow the attached `{UI_SKILL}` skill, or load it with "
                               "the Skill tool if it is not attached. Check your UI change against it, "
                               "fix what it finds, commit, and report again.")
                return spawn_builder(root, prof, run)
            run["stage"] = "gate"
            return start_gate(root, run)
        finish(run, "needs-human",
               f"Builder reported {v}: " + (section(text, "Blocked") or text.splitlines()[0])[:800])
        return None
    if stage == "gate":
        n = str(run["rounds"]["build"])
        token = run.get("gate_token", {}).get(n)
        if not token:
            return start_gate(root, run)
        gfile = runs_dir(root) / run["id"] / f"gate-{n}.json"
        g = _json_or_none(gfile)
        if not isinstance(g, dict) or g.get("token") != token:
            return gate_action(run)
        if changed_contract(root, prof, run):
            return None
        if P.sha(root) != run["profile_sha"]:
            finish(run, "needs-human", "The factory profile changed since this run started. Check the gates before reopening.")
            return None
        if g.get("checkout_changed"):
            finish(run, "needs-human", "The checkout changed while the gates ran in " +
                   ", ".join(g["checkout_changed"]) + ". Review the checkout before reopening.")
            return None
        checkout = repo_checkout(root, prof)
        if g.get("checkout") != checkout:
            if any(s["files"] or s["head"] == "none" or (name in run["repos"] and s["branch"] != run["branch"])
                   for name, s in checkout.items()):
                finish(run, "needs-human", "The checkout changed after the gates ran. Review the workspace before reopening.")
                return None
            event(run, "gate-refresh", reason="Checkout differs from the gate report or the report has no checkout.")
            return start_gate(root, run)
        run.setdefault("gate_sha", {})[n] = _file_sha(gfile)
        skipped = [r for r in g["results"] if r["status"] == "skipped"]
        if skipped:
            finish(run, "needs-human", "Gates not run on this machine, so the change is not verified: " +
                   "; ".join(f"`{r['id']}` ({r.get('reason')})" for r in skipped))
            return None
        if g["ok"]:
            return spawn_reviewers(root, prof, run, checkout)
        run["rounds"]["gate_fail"] += 1
        if run["rounds"]["gate_fail"] > MAX_GATE_FAILS:
            finish(run, "needs-human", "Gates still red after the builder's fix rounds:\n" + gate_digest(g))
            return None
        write_feedback(root, run, "The factory gate failed. Fix the causes, not the checks.\n\n" + gate_digest(g, tails=True))
        return spawn_builder(root, prof, run)
    if stage == "review":
        texts = {s: result(root, run, s) for s in run["review_stems"]}
        missing = [s for s, t in texts.items() if t is None]
        if missing:
            return respawn_or_fail(root, prof, run, REVIEW_ROLES[missing[0].split("-")[0]], missing[0])
        if tampered(root, prof, run, "reviewers"):
            return None
        if changed_contract(root, prof, run):
            return None
        invalid = [s for s, t in texts.items() if verdict(t) not in VALID_VERDICTS[REVIEW_ROLES[s.split("-")[0]]]]
        if invalid:
            finish(run, "needs-human", f"{', '.join(invalid)} returned no valid VERDICT line, so the "
                                                    f"review cannot count as passed.")
            return None
        blocked = [s for s, t in texts.items() if s.startswith("ui-") and verdict(t) == "BLOCKED"]
        if blocked:
            finish(run, "needs-human", "UI change not checked live: " +
                   (section(texts[blocked[0]], "Blocked") or "the ui-tester could not render it")[:800])
            return None
        must_fix = []
        for stem, text in texts.items():
            for m in FINDING.finditer(text):
                if m.group(1).lower() in ("blocker", "required"):
                    must_fix.append(stem)
                    break
            if verdict(text) == "CHANGES" and stem not in must_fix:
                must_fix.append(stem)
        if not must_fix:
            for stem, text in texts.items():
                if not stem.startswith("ui-"):
                    continue
                check = section(text, "Browser check")
                visual = T.header((Path(root) / run["ticket"]).read_text(), "UI-Proof") == "screenshots"
                fields = ["Browser", "Screen", "Observation"] + (["Narrow", "Wide"] if visual else [])
                if not all(re.search(rf"(?im)^{field}:[ \t]*\S", check) for field in fields):
                    finish(run, "needs-human", "UI review supplied no browser check.")
                    return None
                local = runs_dir(root) / run["id"]
                images = archive_screenshots(local, stem, text)
                captions = re.findall(r"(?m)^-\s+`?(/tmp/factory-ui-[\w-]+/[\w.-]+\.(?:png|jpe?g|webp))`?\s*:\s*(.+)$",
                                      section(text, "Screenshots"))
                views = {view: {path for path, caption in captions if path in images and
                                re.search(rf"\b{view}\b", caption, re.I)} for view in ("narrow", "wide")}
                if visual and not any(n != w for n in views["narrow"] for w in views["wide"]):
                    finish(run, "needs-human", "UI review supplied no required screenshots.")
                    return None
                run.setdefault("ui_captures", {})[stem] = images
            return deliver(root, prof, run, texts)
        if run["rounds"]["review"] >= MAX_REVIEW_ROUNDS:
            finish(run, "needs-human", f"Review still asks for changes after {MAX_REVIEW_ROUNDS} rounds; see run {run['id']}.")
            return None
        write_feedback(root, run, "Reviewers asked for changes. Fix every blocker and required finding; nits are optional.\n\n" +
                       "\n\n".join(f"## {s}\n{texts[s]}" for s in must_fix))
        return spawn_builder(root, prof, run)
    return None


def changed_contract(root, prof, run):
    effort = run.get("effort") or run["ticket_ref"].rsplit("/", 1)[0]
    cfg = tracker_cfg(prof)
    revision = T.contract_revision(root, cfg, effort)
    if revision != run.get("contract") or (revision is not None and
            effort in T.contract_issues(root, cfg, T.load(root, cfg))):
        reason = "The feature contract or its ticket revisions changed during this run. Reconcile the effort's tickets."
    elif run.get("ticket_sha") and run["ticket_sha"] != _file_sha(Path(root) / run["ticket"]):
        reason = "The ticket changed during this run."
    elif run.get("stacked_on"):
        tickets, latest = ticket_history(root, cfg)
        path = K.rejected_base(run, tickets, latest, cfg["status"])
        for name, base in run.get("stack_bases", {}).items():
            ticket = tickets.get(base["ticket"])
            if ticket and ticket.status == cfg["status"]["ready"] and git(
                    Path(root) / name, "rev-parse", "--verify", f"refs/heads/{base['branch']}",
                    check=False) != base["head"]:
                path = base["ticket"]
                break
        if not path:
            return False
        reason = f"Stacked base changed or was rejected: {path}."
    else:
        return False
    finish(run, "needs-human", reason + " Reopen this ticket to start a new run.")
    return True


def start_build(root, prof, run, brief):
    names = {r["path"]: r for r in prof["repos"]}
    branch = line_field(brief, "BRANCH")
    repos = [x.strip().strip("`") for x in line_field(brief, "REPOS").split(",") if x.strip()]
    rx = prof["conventions"].get("branch_regex")
    problems = []
    if not branch or (rx and not re.match(rx, branch)):
        problems.append(f"BRANCH '{branch}' does not match {rx}")
    unknown = [r for r in repos if r not in names]
    if not repos or unknown:
        problems.append(f"REPOS must list repos from the profile; unknown: {unknown or 'none given'}")
    prior = [r for r in all_runs(root) if r.get("ticket") == run["ticket"] and r["id"] != run["id"]]
    for name in [] if unknown or not branch else repos:
        repo = Path(root) / name
        if git_ok(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"):
            owners = [r for r in prior if r.get("branch") == branch and name in r.get("repos", [])]
            if not owners:
                problems.append(f"branch {branch} already exists in {name} and belongs to no earlier run of this ticket")
            elif owners[-1].get("stacked_on", {}) != run.get("stacked_on", {}):
                problems.append(f"branch {branch} in {name} was built on different dependencies; choose a new branch")
    if problems:
        if not run.get("brief_retry"):
            run["brief_retry"] = True
            run["pending"] = {}
            return spawn(root, prof, run, [("researcher", "research")], context_for(root, prof, run),
                         extra="\n# Your first brief was refused\n" + "\n".join(f"- {p}" for p in problems) + "\n")
        finish(run, "needs-human", "Research brief unusable: " + "; ".join(problems))
        return None
    for name in repos:
        path = Path(root) / name
        base = (run.get("research_bases", {}).get(name) or run.get("stack_bases", {}).get(name, {}).get("head")
                or names[name]["base"])
        run["base"][name] = git(path, "rev-parse", base)
        if git_ok(path, "rev-parse", "--verify", branch):
            git(path, "switch", branch)
        else:
            git(path, "switch", "-c", branch, base)
    run.update(repos=repos, branch=branch)
    event(run, "branches", branch=branch, repos=repos)
    given = (re.findall(r"[a-z]+", line_field(brief, "DIFFICULTY").lower()) or [""])[0]
    run["difficulty"] = given if given in DIFFICULTY_MODELS else "medium"
    event(run, "difficulty", level=run["difficulty"], given=given)
    return spawn_builder(root, prof, run)


def gate_digest(g, tails=False):
    out = [f"- convention: {p}" for p in g.get("problems", [])]
    for r in g.get("results", []):
        if r["status"] == "fail":
            out.append(f"- gate `{r['id']}` failed (`{r['cmd']}` in `{r['repo']}`, exit {r.get('exit')}, counts {r.get('counts')})")
            if tails:
                out.append("```\n" + r.get("tail", "") + "\n```")
    return "\n".join(out) or "- no detail"


def deliver(root, prof, run, review_texts):
    n = str(run["rounds"]["build"])
    gfile = latest_gate(root, run)
    if not gfile or _file_sha(gfile) != run.get("gate_sha", {}).get(n):
        finish(run, "needs-human", "The gate report changed after the gate ran; the delivery is not trusted.")
        return None
    g = read_json(gfile) or {}
    if g.get("checkout") != repo_checkout(root, prof) or P.sha(root) != run["profile_sha"]:
        finish(run, "needs-human", "The checkout or profile no longer matches the gate evidence. Run the gates again before delivery.")
        return None
    build = result(root, run, f"build-{run['rounds']['build']}") or ""
    brief = result(root, run, "research") or ""
    verified = []
    for r in g.get("results", []):
        if r["status"] == "skipped":
            verified.append(f"- `{r['cmd']}` ({r['repo']}): not run, {r['reason']}")
        else:
            c = r.get("counts")
            verified.append(f"- `{r['cmd']}` ({r['repo']}): exit {r['exit']}" + (f", {c['passed']} passed, {c['failed']} failed" if c else ""))
    for stem, text in review_texts.items():
        verified.append(f"- {stem}: {verdict(text)}")
    nits = [m.group(0).strip() for t in review_texts.values() for m in re.finditer(r"^\s*-\s*\[nit\].*$", t, re.M | re.I)]
    ctype = line_field(brief, "COMMIT_TYPE") or "FEAT"
    stacked = "\n".join(f"- `{name}` is stacked on `{base['branch']}` at `{base['head']}`."
                        for name, base in run.get("stack_bases", {}).items() if name in run["repos"])
    pr = (f"{ctype}: {run['title']}\n\n## Problem\n{section(brief, 'Problem')}\n\n## Change\n{section(build, 'Change')}\n\n"
          + (f"## Merge order\n{stacked}\n\n" if stacked else "")
          + "## Verified\n" + "\n".join(verified) + "\n" + (("\nOpen nits:\n" + "\n".join(nits) + "\n") if nits else ""))
    (runs_dir(root) / run["id"] / "pr.md").write_text(pr)
    pr_path = (archive_path(root, prof, run) / "pr.md").relative_to(root)
    finish(run, "delivered", f"Built on branch `{run['branch']}` in {', '.join(run['repos'])}. "
                                         f"Review it and merge, or set Status back to open with a comment saying what is wrong. "
                                         f"PR text: `{pr_path}`")
    return None


# ---- learn runs ---------------------------------------------------------------------------------

def start_learn(root, prof, key, evidence):
    rid = allocate_run_id(root, "learn")
    run = {"id": rid, "type": "learn", "stage": "learn", "signal": key, "evidence_runs": evidence["runs"],
           "factory_head": git(PLUGIN_ROOT, "rev-parse", "HEAD"),
           "factory_branch": git(PLUGIN_ROOT, "branch", "--show-current"), "proposal_only": True,
           "pending": {}, "rounds": {"build": 0, "review": 0},
           "started": now(), "ended": None, "outcome": None, "events": []}

    run["learn_context"] = (f"- Factory repository: {PLUGIN_ROOT} at {run['factory_head']}\n"
                            f"- Signal: {key} ({len(evidence['runs'])} runs)\n\n## Evidence\n\n{evidence['digest']}\n")
    action = spawn(root, prof, run, [("learner", "learn")], lambda _role, _stem: run["learn_context"])
    save_run(root, run)
    set_active(root, rid)
    return action


def builder_tree_digest(path):
    if not Path(path).is_dir() or Path(path).is_symlink():
        raise FactoryError("Builder replay checkout is missing.")
    digest = hashlib.sha256()
    for file in sorted(Path(path).rglob("*")):
        if ".git" in file.relative_to(path).parts or "__pycache__" in file.parts:
            continue
        if file.is_symlink():
            raise FactoryError("Replay checkout contains a symlink.")
        if file.is_file():
            digest.update(str(file.relative_to(path)).encode() + b"\0" + file.read_bytes() + b"\0")
    return digest.hexdigest()


def builder_replay(root, prof, run, candidate, recipe):
    evidence = runs_dir(root) / run["id"] / "builder-replay"
    base = run["factory_head"]
    if "builder_replay" not in run:
        evidence.mkdir(parents=True, exist_ok=True)
        files = git(PLUGIN_ROOT, "ls-tree", "-r", "--name-only", base, "--", recipe["fixture"]).splitlines()
        if not files or any(not f.startswith(recipe["fixture"] + "/") for f in files):
            raise FactoryError("Builder replay fixture is missing.")
        check = git(PLUGIN_ROOT, "show", f"{base}:{recipe['checks']}", strip=False)
        (evidence / "checks.py").write_text(check)
        (evidence / "recipe.json").write_text(json.dumps(recipe, indent=2) + "\n")
        for stem in ("replay-baseline", "replay-candidate"):
            checkout = evidence / stem
            checkout.mkdir()
            for file in files:
                entry = git(PLUGIN_ROOT, "ls-tree", base, "--", file)
                if not entry.startswith("100644 blob "):
                    raise FactoryError("Replay fixture must contain regular files.")
                target = checkout / file[len(recipe["fixture"]) + 1:]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(git(PLUGIN_ROOT, "show", f"{base}:{file}", strip=False))
            git(checkout, "init", "-q")
            git(checkout, "add", ".")
            git(checkout, "-c", "user.name=Factory", "-c", "user.email=factory@example.com", "-c", "commit.gpgsign=false",
                "commit", "-qm", "CHORE: replay fixture")
        run["builder_replay"] = {"inputs": builder_tree_digest(evidence / "replay-baseline"),
                                 "checks": hashlib.sha256(check.encode()).hexdigest(), "base": base}
    state = run["builder_replay"]
    if ((evidence / "recipe.json").read_text() != json.dumps(recipe, indent=2) + "\n" or
            hashlib.sha256((evidence / "checks.py").read_bytes()).hexdigest() != state["checks"]):
        raise FactoryError("Builder replay inputs changed.")
    baseline = evidence / "replay-baseline"
    if "baseline_digest" in state and builder_tree_digest(baseline) != state["baseline_digest"]:
        raise FactoryError("Builder replay baseline checkout changed after scoring.")
    for stem, instructions in (("replay-baseline", candidate["before"]), ("replay-candidate", candidate["after"])):
        checkout = evidence / stem
        if stem not in state:
            answer = result(root, run, stem)
            if answer is None:
                if stem not in run.get("spawn_ids", {}) and builder_tree_digest(checkout) != state["inputs"]:
                    raise FactoryError("Builder replay starting checkout changed.")
                run["stage"] = stem
                prompt = (f"Work only in {checkout}. This is a disposable Git checkout. "
                          f"Starting code is committed. Task: {recipe['task']}\n"
                          "This replay has no ticket, brief, branch requirement, or prescribed gates; "
                          "ignore those normal run instructions. Commit or leave your patch in this checkout. "
                          "Return your normal builder verdict when finished. The owner runs acceptance checks independently.")
                return await_learning_agent(root, prof, run, "builder", stem, lambda _role, _stem: prompt, instructions)
            builder_tree_digest(checkout)
            try:
                check = subprocess.run([sys.executable, str(evidence / "checks.py"), str(checkout)],
                                       capture_output=True, text=True, timeout=30)
                scores = json.loads(check.stdout)
            except (ValueError, OSError, subprocess.TimeoutExpired) as e:
                raise FactoryError(f"{stem} acceptance checks did not produce scores.") from e
            if check.returncode or not isinstance(scores, dict) or not scores or any(type(v) is not bool for v in scores.values()):
                raise FactoryError(f"{stem} acceptance checks failed to run.")
            state[stem] = scores
            state[stem + "_digest"] = builder_tree_digest(checkout)
            write_json(evidence / (stem + "-checks.json"), {"scores": scores, "stdout": check.stdout, "stderr": check.stderr})
            if stem == "replay-baseline":
                state["baseline_digest"] = state[stem + "_digest"]
                if all(scores.values()):
                    raise FactoryError("Baseline already passes every replay check.")
    if (S.checkout_changed(run) or (evidence / "recipe.json").read_text() != json.dumps(recipe, indent=2) + "\n" or
            hashlib.sha256((evidence / "checks.py").read_bytes()).hexdigest() != state["checks"]):
        raise FactoryError("Builder replay inputs changed during scoring.")
    old, new = state["replay-baseline"], state["replay-candidate"]
    if old.keys() != new.keys() or any(old[k] and not new[k] for k in old) or not any(not old[k] and new[k] for k in old):
        raise FactoryError("Builder replay did not improve while preserving passing checks.")
    if builder_tree_digest(baseline) != state["baseline_digest"] or builder_tree_digest(evidence / "replay-candidate") != state["replay-candidate_digest"]:
        raise FactoryError("Builder replay checkout changed after scoring.")
    return None


def advance_learn(root, prof, run):
    if not run.get("proposal_only") or S.checkout_changed(run):
        reason = f"The factory checkout {PLUGIN_ROOT} changed outside learner run {run['id']}. Review it before restarting learning."
        if not run.get("proposal_only"):
            reason = "This learner run predates isolated proposals. Review the checkout before restarting learning."
        finish(run, "interrupted", reason)
        return {"action": "STOP", "reason": reason}
    text = result(root, run, "learn")
    if run["stage"] == "learn" and text is None:
        return await_learning_agent(root, prof, run, "learner", "learn",
                                    lambda _role, _stem: run["learn_context"])
    key, evidence = run["signal"], run["evidence_runs"]
    if verdict(text) == "NO-CHANGE":
        S.mark_covered(root, key, evidence, None, "NO-CHANGE")
        finish(run, "no-change", section(text, "Human"))
        return None
    try:
        if verdict(text) != "CHANGED":
            raise FactoryError("Learner must return CHANGED or NO-CHANGE.")
        proposal = section(text, "Candidate")
        fence = re.fullmatch(r"```json\n(.*)\n```", proposal, re.S)
        candidate = S.prepare_candidate(run["factory_head"], fence[1] if fence else proposal)
        cases = S.replay_cases(run["factory_head"], key, candidate["path"])
        if not cases:
            reason = f"Proposal in {result_path(root, run, 'learn')} awaits independent replay cases."
            S.mark_tried(root, key, evidence, [reason], "proposed")
            finish(run, "proposed", reason)
            return None
        if candidate["path"] == "roles/builder.md":
            try:
                action = builder_replay(root, prof, run, candidate, cases)
            except OSError as e:
                raise FactoryError("Builder replay inputs are missing or unreadable.") from e
            if action is not None:
                return action
            commit = S.adopt_candidate(run, candidate)
            S.mark_covered(root, key, evidence, commit, "CHANGED")
            finish(run, "changed", f"Adopted {candidate['path']} at {commit}.")
            return None
        role = "researcher" if candidate["path"] == "roles/researcher.md" else "reviewer"
        outcomes = ("READY", "NEEDS-INFO") if role == "researcher" else ("PASS", "CHANGES")
        task = "Plan" if role == "researcher" else "Review"
        prompt = (f"\n{task} each case separately using the instructions above. Use only the supplied case text. "
                  "Return VERDICT: REPLAYED and a '## Results' section containing a JSON object that maps "
                  f"each case ID to {outcomes[0]} or {outcomes[1]}.\n\n" +
                  json.dumps({label: case["prompt"] for label, case in cases.items()}, indent=2))
        expected = {label: case["expected"] for label, case in cases.items()}
        for stem, instructions in (("replay-baseline", candidate["before"]), ("replay-candidate", candidate["after"])):
            answer = result(root, run, stem)
            if answer is None:
                run["stage"] = stem
                return await_learning_agent(root, prof, run, role, stem, lambda _role, _stem: prompt, instructions)
            report = section(answer, "Results")
            fence = re.fullmatch(r"```json\n(.*)\n```", report, re.S)
            scores = json.loads(fence[1] if fence else report)
            if (verdict(answer) != "REPLAYED" or not isinstance(scores, dict) or scores.keys() != expected.keys() or
                    any(value not in outcomes for value in scores.values())):
                raise FactoryError(f"{stem} did not return a verdict for every replay case.")
            if stem == "replay-baseline" and scores == expected:
                raise FactoryError("Baseline already passes every replay case.")
            if stem == "replay-candidate" and scores != expected:
                raise FactoryError("Candidate did not pass every replay case.")
        commit = S.adopt_candidate(run, candidate)
    except (FactoryError, ValueError) as e:
        S.mark_tried(root, key, evidence, [str(e)])
        finish(run, "rejected", str(e))
        return None
    S.mark_covered(root, key, evidence, commit, "CHANGED")
    finish(run, "changed", f"Adopted {candidate['path']} at {commit}.")
    return None


def await_learning_agent(root, prof, run, role, stem, context, instructions=None):
    if stem in run["pending"].values():
        return respawn_or_fail(root, prof, run, role, stem)
    if run.get(f"respawn:{stem}"):
        reason = f"{stem} returned no result twice."
        S.mark_tried(root, run["signal"], run["evidence_runs"], [reason])
        finish(run, "rejected", reason)
        return None
    if stem in run.get("spawn_ids", {}):
        run[f"respawn:{stem}"] = True
    run["pending"] = {}
    return spawn(root, prof, run, [(role, stem)], context, instructions=instructions)


# ---- entry points -------------------------------------------------------------------------------

def all_runs(root):
    out = []
    paths = {f.parent.name: f for directory in archive_dirs(root) for f in directory.glob("*/run.json")}
    paths.update({f.parent.name: f for f in runs_dir(root).glob("*/run.json")})
    for _, f in sorted(paths.items()):
        r = read_json(f)
        if r:
            out.append(r)
    return out


def ticket_history(root, cfg):
    tickets = {t.path: t for t in T.load(root, cfg)}
    latest = {r["ticket"]: r for r in all_runs(root) if r.get("ticket") in tickets}
    return tickets, latest


def feature_evidence(root, effort):
    """Describe which ticket deliveries are covered by the current implementation checkout."""
    prof = P.load(root)
    cfg = tracker_cfg(prof)
    tickets, latest = ticket_history(root, cfg)
    feature = [t for t in tickets.values() if t.effort == effort and t.type in cfg["build_types"]]
    if not feature:
        raise FactoryError(f"No build tickets for effort {effort!r}.")
    revision = T.contract_revision(root, cfg, effort)
    code = {}
    ignored = (".factory/", cfg["root"].rstrip("/") + "/")
    for repo in prof["repos"]:
        name = repo["path"]
        path = Path(root) / name
        initialized = git(path, "rev-parse", "--show-toplevel", check=False) == str(path.resolve())
        code[name] = {"head": git(path, "rev-parse", "HEAD", check=False) if initialized else None,
                      "dirty": bool(dirty_paths(path, ignored if name == "." else ())) if initialized else None}
        if name != ".":
            entry = git(root, "ls-tree", "HEAD", "--", name, check=False)
            if entry.startswith("160000 commit "):
                code[name]["parent_head"] = entry.split()[2]
    deliveries = []
    for ticket in feature:
        row = {"ticket": ticket.ref, "path": ticket.path, "status": ticket.status,
               "ticket_revision": _file_sha(Path(root) / ticket.path)}
        deliveries.append(row)
        if ticket.status in {"wontfix", "superseded", "declined"}:
            row["delivery"] = "discarded"
            continue
        if ticket.status not in {*cfg["status"]["done"], cfg["status"]["ready"]}:
            row["delivery"] = "unfinished"
            continue
        run = latest.get(ticket.path, {})
        heads = run.get("reviewed_heads", {})
        if run.get("outcome") != "delivered" or not heads:
            row["delivery"] = "no recorded review"
            continue
        row["run"] = str(run_dir(root, run["id"]).relative_to(root))
        row["reviewed_heads"] = heads
        if run.get("contract") != revision:
            row["delivery"] = "previous contract"
        elif K.rejected_base(run, tickets, latest, cfg["status"]):
            row["delivery"] = "base delivery superseded"
        elif any(name not in code or not code[name]["head"] or not git_ok(
                Path(root) / name, "merge-base", "--is-ancestor", commit, code[name]["head"])
                for name, commit in heads.items()):
            row["delivery"] = "reviewed commits need current proof"
        else:
            row["delivery"] = "reviewed commits present"
        number = str(run["rounds"]["build"])
        gate = run_dir(root, run["id"]) / f"gate-{number}.json"
        if run.get("gate_sha", {}).get(number) == _file_sha(gate) and gate.is_file():
            report = read_json(gate)
            tested = report.get("checkout", {})
            if not report["ok"]:
                row["gate"] = "failed at delivery"
            elif all(tested.get(name, {}).get("head") == commit for name, commit in heads.items()):
                row["gate"] = "passed at delivery"
            else:
                row["gate"] = "historical pass needs commit proof"
    return {"contract": revision, "checkout": code, "tickets": deliveries,
            "dependency_issues": list(T.dependency_issues(feature, cfg))}


def work_queue(root, cfg, tickets, latest):
    blocked = {path for path, t in tickets.items() if delivery_problem(root, cfg, t, tickets, latest)}
    for ticket in T.frontier(root, cfg, tickets=tickets.values(), include_delivered=True):
        plan = K.plan(root, ticket, tickets, latest, cfg["status"])
        if plan is not None and not blocked.intersection(plan["stacked_on"]):
            yield ticket, plan


def delivery_problem(root, cfg, ticket, tickets, latest):
    statuses = cfg["status"]
    run = latest.get(ticket.path, {})
    if ticket.status != statuses["ready"] or run.get("outcome") != "delivered":
        return None
    base = K.rejected_base(run, tickets, latest, statuses)
    if base:
        return f"Base ticket {tickets[base].ref if base in tickets else base} was rejected or replaced. Review this stack before reopening."
    if run.get("contract") != T.contract_revision(root, cfg, ticket.effort):
        return "This delivery used a previous feature contract. Review the branch against the current contract."
    if T.awaiting_plan(ticket, cfg):
        return "The issue plan changed after approval. Review the delivery before reopening."
    return None


def park_deliveries(root, cfg, tickets, latest):
    for path, ticket in tickets.items():
        reason = delivery_problem(root, cfg, ticket, tickets, latest)
        if reason:
            T.set_status(root, path, cfg["status"]["parked"])
            T.comment(root, path, reason)
            ticket.status = cfg["status"]["parked"]


def board(root, effort=None):
    """Project the tracker and queue into review and work columns without changing either."""
    cfg = tracker_cfg(P.load(root))
    status = cfg["status"]
    tickets, latest = ticket_history(root, cfg)
    ready = {t.path for t, _ in work_queue(root, cfg, tickets, latest)}
    stale = T.contract_issues(root, cfg, tickets.values())
    active = state(root).get("active")
    active_run = _json_or_none(runs_dir(root) / active / "run.json") if active else None
    columns = {name: [] for name in ("Draft", "Plan review", "Backlog", "In progress",
                                    "Ready for code review", "Needs attention", "Done / closed")}
    for t in tickets.values():
        if t.type not in cfg["build_types"] or (effort is not None and t.effort != effort):
            continue
        note = delivery_problem(root, cfg, t, tickets, latest)
        if t.status in status["done"]:
            column = "Done / closed"
        elif t.status == status["claimed"]:
            if active_run and active_run.get("ticket") == t.path:
                column = "In progress"
            else:
                column, note = "Needs attention", "Claimed without an active factory run"
        elif t.status in (status["needs_human"], status["parked"]) or note:
            column = "Needs attention"
        elif t.status == status["ready"]:
            column = "Ready for code review"
        elif t.status in ("draft", status["needs_info"]):
            column = "Draft"
        elif t.effort in stale or T.awaiting_plan(t, cfg):
            column = "Plan review"
            if t.effort in stale:
                note = "Reconcile the current contract"
            elif t.status == status["plan_changes"]:
                note = "Changes requested in Plannotator"
        elif t.status in status["queue"]:
            column = "Backlog"
            note = None if t.path in ready else "Waiting for dependencies or a runnable branch"
        else:
            column = "Draft"
        columns[column].append({"ref": t.ref, "path": t.path, "title": t.title, "status": t.status, "note": note})
    return columns


def next_action(root, force_ticket=None, *, learn_only=False):
    with state_lock(root, wait=False) as acquired:
        if not acquired:
            return {"action": "STOP", "reason": "Another factory command is updating this project. Retry after it returns."}
        note = []
        act = _next_action(root, force_ticket, note, learn_only)
        if note:
            act["note"] = note[0]
        return act


def _next_action(root, force_ticket, note, learn_only):
    prof = P.load(root)
    cfg = tracker_cfg(prof)
    for _ in range(50):
        rid = state(root).get("active")
        if rid:
            run = load_run(root, rid)
            if learn_only and run["type"] != "learn":
                return {"action": "STOP", "reason": "A ticket run is active. Continue it with /factory:run."}
            act = None
            if not run.get("ended"):
                if force_ticket:
                    try:
                        chosen = T.find(root, cfg, force_ticket)
                    except FactoryError as e:
                        return {"action": "STOP", "reason": str(e)}
                    if chosen is None or run.get("ticket") != chosen.path:
                        active = run.get("ticket_ref") or run["id"]
                        return {"action": "STOP", "reason": f"Run {active} is active. Finish it before starting {force_ticket}."}
                if "before_claim" in run:
                    try:
                        act = complete_claim(root, prof, cfg, run)
                    except OSError as e:
                        return {"action": "STOP", "reason": f"Could not claim {run['ticket_ref']}: {e}. Retry factory next."}
                if act is None:
                    act = advance_learn(root, prof, run) if run["type"] == "learn" else advance(root, prof, run)
                save_run(root, run)
            if act:
                return act
            if not run.get("ended"):
                return {"action": "STOP", "reason": f"Run {rid} stopped in unknown stage {run['stage']!r}."}
            if run["type"] == "ticket":
                try:
                    archive_run(root, prof, run)
                    finalize_ticket(root, cfg, run)
                except OSError as e:
                    return {"action": "STOP", "reason": f"Could not finish storing run {rid}: {e}. Retry factory next."}
            set_active(root, None)
            continue
        if learn_only:
            return {"action": "IDLE", "summary": status_lines(root)}
        pending = pending_claims(root)
        if len(pending) > 1:
            return {"action": "STOP", "reason": "Multiple unconfirmed ticket runs: " + ", ".join(pending)}
        if pending:
            set_active(root, pending[0])
            continue
        tickets, latest = ticket_history(root, cfg)
        park_deliveries(root, cfg, tickets, latest)
        if not force_ticket:
            pending = S.pending_signals(root)
            if pending and dirty_paths(PLUGIN_ROOT):
                note[:] = ["learning skipped: the factory checkout has uncommitted changes"]
            elif pending:
                key, evidence = pending[0]
                return start_learn(root, prof, key, evidence)
        queue = work_queue(root, cfg, tickets, latest)
        try:
            chosen = T.find(root, cfg, force_ticket) if force_ticket else None
        except FactoryError as e:
            return {"action": "STOP", "reason": str(e)}
        if force_ticket and chosen is None:
            return {"action": "STOP", "reason": f"Unknown ticket {force_ticket}"}
        if chosen:
            stale = T.contract_issues(root, cfg, tickets.values()).get(chosen.effort)
            if stale:
                return {"action": "STOP", "reason": f"Update these tickets to the current feature contract: {', '.join(stale)}"}
            if chosen.type in cfg["build_types"] and T.awaiting_plan(chosen, cfg):
                return {"action": "STOP", "reason": f"{chosen.ref} needs Plannotator plan approval."}
            entry = next((pair for pair in queue if pair[0].path == chosen.path), None)
            if entry is None:
                return {"action": "STOP", "reason": f"{chosen.ref} is not runnable. Check its status and dependencies."}
        else:
            entry = next(queue, None)
        if entry is None:
            return {"action": "IDLE", "summary": status_lines(root)}
        force_ticket = None
        ticket, plan = entry
        blocked = preflight(root, prof)
        if blocked:
            return {"action": "STOP", "reason": blocked}
        try:
            run = new_run(root, prof, ticket, plan)
            set_active(root, run["id"])
        except (FactoryError, OSError) as e:
            return {"action": "STOP", "reason": str(e)}
    raise FactoryError("next_action looped 50 times; inspect .factory/state.json")


def record(root, rid, stem, spawn, text):
    """Fallback when the hook did not store a result: only for the awaited spawn of a pending stem."""
    with state_lock(root):
        run = load_run(root, rid)
        if stem not in run["pending"].values() or run.get("spawn_ids", {}).get(stem) != spawn:
            raise FactoryError(f"{stem} #{spawn} is not an awaited result of run {rid}; nothing recorded")
        store_result(root, rid, stem, spawn, text, "record")
        event(run, "recorded-by-orchestrator", stem=stem, spawn=spawn)
        save_run(root, run)


def release(root, rid, stem):
    """Human only: drop a started agent that will never deliver, so the next action starts it once more."""
    with state_lock(root):
        run = load_run(root, rid)
        if run.get("ended"):
            raise FactoryError(f"run {rid} has already finished")
        run["pending"] = {k: v for k, v in run["pending"].items() if v != stem}
        run.setdefault("spawn_ids", {})[stem] = None      # a late result of the released agent never counts
        event(run, "released-by-human", stem=stem)
        save_run(root, run)


def wait_agents(root, rid, wait=540, poll=5):
    """Block until every started agent's result is proven, up to `wait` seconds. Re-reads the run on every poll."""
    deadline = time.time() + wait
    while True:
        with state_lock(root):
            run = load_run(root, rid)
            missing = [f"{s}#{run.get('spawn_ids', {}).get(s)}" for s in run["pending"].values()
                       if not overdue(root, run, s) and result(root, run, s) is None]
        if not missing:
            return "DONE"
        if time.time() >= deadline:
            return "RUNNING " + " ".join(missing)
        time.sleep(poll)


def gate(root, rid, wait=540):
    """Start the gate runner detached (if not running) and wait for this round's result (matching token)."""
    proc = None
    with state_lock(root):
        run = load_run(root, rid)
        if run.get("ended"):
            path = latest_gate(root, run)
            if not path:
                raise FactoryError(f"run {rid} has no gate report")
            report = read_json(path)
            return ("PASS" if report["ok"] else "FAIL") + "\n" + gate_digest(report)
        n = str(run["rounds"]["build"])
        token = run.get("gate_token", {}).get(n)
        filename = f"gate-{n}.json"
        out = runs_dir(root) / rid / filename
        report = _json_or_none(out)
        if token and isinstance(report, dict) and report.get("token") == token:
            return ("PASS" if report["ok"] else "FAIL") + "\n" + gate_digest(report)
        if run["stage"] != "gate":
            raise FactoryError(f"Run {rid} has no current gate report for build round {n}.")
        if not token:
            raise FactoryError(f"Run {rid} is not waiting for a gate in build round {n}.")
        out.unlink(missing_ok=True)
        lock = out.with_suffix(".lock")
        pid = lock.read_text().strip() if lock.is_file() else ""
        if not pid.isdecimal() or not _alive(int(pid)):
            with (runs_dir(root) / rid / "gate-runner.log").open("a") as log:
                proc = subprocess.Popen([sys.executable, str(FACTORY_BIN), "gate-run", rid, token],
                                        cwd=root, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
            atomic_write_text(lock, str(proc.pid))
    deadline = time.time() + wait
    while True:
        with state_lock(root):
            current = load_run(root, rid)
            report = _json_or_none(run_dir(root, rid) / filename)
            if isinstance(report, dict) and report.get("token") == token:
                if proc is not None:
                    proc.poll()
                return ("PASS" if report["ok"] else "FAIL") + "\n" + gate_digest(report)
            if current.get("ended") or str(current["rounds"]["build"]) != n or current.get("gate_token", {}).get(n) != token:
                return "SUPERSEDED"
        if proc is not None and proc.poll() not in (None, 0):
            raise FactoryError(f"The gate runner failed before writing a report. See {out.parent / 'gate-runner.log'}.")
        if time.time() >= deadline:
            return "RUNNING"
        time.sleep(5)


def _alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def gate_run(root, rid, token=None):
    prof = P.load(root)
    run = load_run(root, rid)
    if run.get("ended"):
        raise FactoryError(f"run {rid} has already finished")
    n = run["rounds"]["build"]
    if run["stage"] != "gate" or not token or token != run.get("gate_token", {}).get(str(n)):
        raise FactoryError(f"Gate round {n} of run {rid} is no longer active.")
    checkout = repo_checkout(root, prof)
    touched = G.touched_repos(root, prof, run)
    problems = G.check_conventions(root, prof, run, run["repos"])
    if not touched:
        problems.append("no commits on the run branch in any repo")
    results = []
    profile_matches = P.sha(root) == run["profile_sha"]
    if profile_matches:
        for name in touched:
            for g in G.gates_for(prof, name, G.changed_files(root, run, name, checkout[name]["head"])):
                results.append(G.run_gate(root, g, runs_dir(root) / rid / f"gate-{n}" / f"{g['id'].replace(':', '_')}.log"))
    problems += [p for p in G.check_conventions(root, prof, run, run["repos"]) if p not in problems]
    if not profile_matches or P.sha(root) != run["profile_sha"]:
        problems.append(".factory/profile.json changed during the run")
    after = repo_checkout(root, prof)
    changed = [name for name, before in checkout.items() if after[name] != before]
    if changed:
        problems.append("checkout changed while the gates ran: " + ", ".join(changed))
    ok = not problems and all(r["ok"] is True for r in results)      # a skipped gate is not a pass
    with state_lock(root):
        current = load_run(root, rid)
        if current["stage"] == "gate" and current["rounds"]["build"] == n and current.get("gate_token", {}).get(str(n)) == token:
            write_json(runs_dir(root) / rid / f"gate-{n}.json", {"ok": ok, "problems": problems, "results": results, "t": now(),
                                                               "token": token, "checkout": checkout, "checkout_changed": changed})


def status_lines(root):
    rows = []
    runs = all_runs(root)
    for r in runs[-15:]:
        rows.append(f"{r['id']}  {r.get('ticket_ref') or r.get('signal')}  {r['stage']}  "
                    f"build rounds {r['rounds'].get('build')}  {r.get('outcome') or 'running'}")
        if r.get("type") == "learn" and r.get("finish_reason"):
            rows.append("  " + r["finish_reason"].splitlines()[0][:300])
    if P.path(root).is_file():
        cfg = tracker_cfg(P.load(root))
        tickets = T.load(root, cfg)
        for effort, stale in T.contract_issues(root, cfg, tickets).items():
            rows.append(f"{effort}: feature contract needs reconciliation in {', '.join(stale)}")
        rows.extend(T.dependency_issues(tickets, cfg))
        active = state(root).get("active")
        claims = {r.get("ticket") for r in runs if r["id"] == active or ("before_claim" in r and not r.get("ended"))}
        for ticket in tickets:
            if (ticket.status == cfg["status"]["claimed"] and ticket.type in cfg["build_types"] and
                    ticket.path not in claims):
                rows.append(f"{ticket.ref}: claimed without an active factory run")
    return "\n".join(rows) or "no runs yet"

"""Learning signals from run records, the learner ledger, and the check that runs after a learner change."""
import collections
import json
import re
import tempfile
from pathlib import Path

from .util import PLUGIN_ROOT, FactoryError, dirty_paths, factory_dir, git, now, read_json, write_json

WINDOW = 10                                   # most recent finished ticket runs considered
THRESHOLD = {"human:rejected": 1}            # one rejection by the human is enough
DEFAULT_THRESHOLD = 2                         # everything else must recur
PROTECTED = ("bin/", "lib/", "hooks/", "tests/", "skills/init/", "skills/run/", "skills/learn/",
             "skills/eval/", ".claude-plugin/", "agents/", "roles/learner.md")
EDITABLE = re.compile(r"(?:roles/[a-z0-9-]+\.md|skills/[a-z0-9-]+/SKILL\.md)")
KINDS = (("commit subject", "commit-subject"), ("uncommitted", "uncommitted"), ("tenant data", "tenant-data"),
         ("submodule pointer", "submodule-pointer"), ("protected file", "protected-file"),
         ("no commits", "no-commits"), ("profile.json", "profile-tamper"), ("branch", "branch"))


def ledger_path(root):
    return factory_dir(root) / "learn.json"


def classify(problem):
    return next((kind for word, kind in KINDS if word in problem), "other")


def collect(root):
    """signal key -> [(run id, evidence excerpt)], one entry per run."""
    from .engine import FINDING, all_runs, result, run_dir
    runs = [r for r in all_runs(root) if r.get("type") == "ticket" and r.get("outcome")][-WINDOW:]
    hits = collections.defaultdict(list)
    for r in runs:
        rdir, keys = run_dir(root, r["id"]), {}
        for gf in sorted(rdir.glob("gate-*.json")):
            g = read_json(gf) or {}
            for res in g.get("results", []):
                if res["status"] == "fail":
                    keys.setdefault(f"gate:{res['id']}", f"{gf.name}: `{res['cmd']}` exit {res.get('exit')}\n"
                                                          f"```\n{res.get('tail', '')[-1500:]}\n```")
            for p in g.get("problems", []):
                keys.setdefault(f"convention:{classify(p)}", f"{gf.name}: {p}")
        for stem in sorted(s for s in r.get("spawn_ids", {}) if s.startswith(("review-", "security-"))):
            text = result(root, r, stem) or ""        # proven results only; stray files never become signals
            for m in FINDING.finditer(text):
                if m.group(1).lower() in ("blocker", "required"):
                    line = text[m.start():text.find("\n", m.start()) if "\n" in text[m.start():] else len(text)]
                    keys.setdefault(f"review:{(m.group(2) or 'general').lower()}", f"{stem}: {line.strip()}")
        if r.get("reopened_from"):
            fb = next(iter(sorted(rdir.glob("feedback-*.md"))), None)
            keys["human:rejected"] = fb.read_text()[:1500] if fb else "ticket reopened"
        if r.get("outcome") == "needs-human":
            reason = next((e.get("reason") for e in reversed(r["events"]) if e["event"] == "finish"), "")
            keys["outcome:needs-human"] = reason
        for k, v in keys.items():
            hits[k].append((r["id"], v))
    return hits


def pending_signals(root):
    """Signals with enough fresh runs that no learner change has covered yet, most urgent first."""
    if not git(PLUGIN_ROOT, "rev-parse", "HEAD", check=False):
        return []          # learning needs a committed baseline
    ledger = read_json(ledger_path(root), {})
    out = []
    for key, items in collect(root).items():
        entry = ledger.get(key, {})
        covered = set(entry.get("runs", [])) | set(entry.get("tried", []))     # a retry needs new runs
        fresh = [(rid, ex) for rid, ex in items if rid not in covered]
        if len(fresh) >= THRESHOLD.get(key, DEFAULT_THRESHOLD):
            digest = "\n\n".join(f"### run {rid}\n{ex}" for rid, ex in fresh[-4:])
            out.append((key, {"runs": [rid for rid, _ in fresh], "digest": digest}))
    out.sort(key=lambda kv: (kv[0] != "human:rejected", -len(kv[1]["runs"])))
    return out


def mark_covered(root, key, runs, commit, verdict):
    ledger = read_json(ledger_path(root), {})
    entry = ledger.setdefault(key, {"runs": [], "changes": []})
    entry["runs"] = sorted(set(entry["runs"]) | set(runs))
    entry["changes"].append({"t": now(), "commit": commit, "verdict": verdict})
    write_json(ledger_path(root), ledger)


def mark_tried(root, key, runs, problems, verdict="rejected"):
    """Keep unresolved evidence from immediately starting the same attempt again."""
    ledger = read_json(ledger_path(root), {})
    entry = ledger.setdefault(key, {"runs": [], "changes": []})
    entry["tried"] = sorted(set(entry.get("tried", [])) | set(runs))
    entry["changes"].append({"t": now(), "commit": None, "verdict": verdict, "problems": problems})
    write_json(ledger_path(root), ledger)


def prepare_candidate(base, proposal):
    """Resolve one exact text replacement against the committed baseline."""
    try:
        patch = json.loads(proposal)
    except ValueError as e:
        raise FactoryError("Candidate must be a JSON object with path, old and new.") from e
    if not isinstance(patch, dict) or patch.keys() != {"path", "old", "new"}:
        raise FactoryError("Candidate must contain exactly path, old and new.")
    path, old, new = (patch[k] for k in ("path", "old", "new"))
    if not isinstance(path, str) or not EDITABLE.fullmatch(path) or path.startswith(PROTECTED):
        raise FactoryError("Candidate targets a protected path.")
    if not isinstance(new, str) or "\0" in new:
        raise FactoryError("Candidate replacement must be text.")
    entry = git(PLUGIN_ROOT, "ls-tree", base, "--", path)
    if entry:
        if not entry.startswith(("100644 blob ", "100755 blob ")):
            raise FactoryError("Candidate must edit a regular file.")
        before = git(PLUGIN_ROOT, "cat-file", "blob", f"{base}:{path}", strip=False)
        if not isinstance(old, str) or not old or before.count(old) != 1:
            raise FactoryError("Candidate old text must match the baseline exactly once.")
        after = before.replace(old, new, 1)
    elif old is None and path.startswith("skills/"):
        before, after = "", new
    else:
        raise FactoryError("Candidate cannot add a role or replace missing text.")
    if not after.strip() or after == before or len(after.splitlines()) > 500:
        raise FactoryError("Candidate must change the file and leave 1 to 500 lines.")
    if path.startswith("skills/"):
        frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", after, re.S)
        fields = set(re.findall(r"^([a-z]+):[ \t]*\S", frontmatter[1], re.M)) if frontmatter else set()
        if not {"name", "description"} <= fields or (not entry and not re.search(r"^origin: learned$", frontmatter[1], re.M)):
            raise FactoryError("Skill needs name and description frontmatter and a new skill needs origin: learned.")
    return {"path": path, "before": before, "after": after}


def replay_cases(base, key, path):
    """Only the factory's committed cases can authorize a paired replay."""
    outcomes = {"roles/reviewer.md": {"PASS", "CHANGES"},
                "roles/researcher.md": {"READY", "NEEDS-INFO"}}
    if path not in outcomes and path != "roles/builder.md":
        return {}
    manifest = git(PLUGIN_ROOT, "show", f"{base}:tests/learning.json", check=False)
    recipe = json.loads(manifest).get(key) if manifest else None
    if not recipe or recipe["path"] != path:
        return {}
    if path == "roles/builder.md":
        if set(recipe) != {"path", "fixture", "checks", "task"} or not all(
                isinstance(recipe[k], str) and recipe[k] for k in ("fixture", "checks", "task")):
            raise FactoryError("Invalid builder replay recipe.")
        if not re.fullmatch(r"tests/fixtures/[a-z0-9-]+", recipe["fixture"]) or not re.fullmatch(
                r"tests/fixtures/[a-z0-9-]+\.py", recipe["checks"]):
            raise FactoryError("Invalid builder replay input path.")
        return recipe
    cases = recipe["cases"]
    if not cases or set(case["expected"] for case in cases.values()) != outcomes[path]:
        raise FactoryError("Learning replay needs both outcomes for the selected role.")
    return cases


def checkout_changed(run):
    return (git(PLUGIN_ROOT, "rev-parse", "HEAD", check=False) != run["factory_head"] or
            git(PLUGIN_ROOT, "branch", "--show-current", check=False) != run.get("factory_branch") or
            bool(dirty_paths(PLUGIN_ROOT)))


def adopt_candidate(run, candidate):
    """Build a commit off to the side, then fast-forward the unchanged installation."""
    with tempfile.TemporaryDirectory(prefix="factory-learn-") as temp:
        worktree = Path(temp) / "candidate"
        git(PLUGIN_ROOT, "worktree", "add", "--detach", str(worktree), run["factory_head"])
        try:
            path = worktree / candidate["path"]
            if path.resolve() != path:
                raise FactoryError("Candidate path points through a symlink.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(candidate["after"])
            git(worktree, "add", "--", candidate["path"])
            git(worktree, "commit", "-m", f"UPT: learn from {run['signal']}",
                "-m", f"Factory-Learn-Run: {run['id']}")
            head = git(worktree, "rev-parse", "HEAD")
            if (git(worktree, "diff", "--name-only", "--no-renames", run["factory_head"], head) != candidate["path"] or
                    git(worktree, "cat-file", "blob", f"{head}:{candidate['path']}", strip=False) != candidate["after"]):
                raise FactoryError("The learning commit differs from the evaluated candidate.")
            if checkout_changed(run):
                raise FactoryError("The factory checkout changed while preparing the learning commit.")
            git(PLUGIN_ROOT, "merge", "--ff-only", "--no-overwrite-ignore", "--no-edit", head)
            return head
        finally:
            git(PLUGIN_ROOT, "worktree", "remove", "--force", str(worktree), check=False)

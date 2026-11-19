"""Keep observations local and turn measured factory problems into ordinary build tickets."""
import hashlib
import json
import re
from pathlib import Path

from . import profile
from .util import PLUGIN_ROOT, FactoryError, factory_dir, read_json, write_json


def observations(root):
    return factory_dir(root) / "evaluations"


def report(root, summary, observed, expected, check):
    item = {"summary": " ".join(summary.split()), "observed": observed.strip(),
            "expected": expected.strip(), "check": check.strip()}
    if not all(item.values()):
        raise FactoryError("an observation needs a summary, actual result, expected result, and replay steps")
    contents = json.dumps(item, sort_keys=True)
    oid = hashlib.sha256(contents.encode()).hexdigest()[:16]
    path = observations(root) / f"{oid}.json"
    if not path.exists():
        write_json(path, item)
    return oid


def load(root, oid):
    if not re.fullmatch(r"[0-9a-f]{16}", oid):
        raise FactoryError("invalid observation ID")
    item = read_json(observations(root) / f"{oid}.json")
    if item is None:
        raise FactoryError(f"unknown observation {oid}")
    return item


def development_checkout(target):
    target = Path(target).resolve()
    if target == PLUGIN_ROOT.resolve():
        raise FactoryError("use a separate factory development checkout")
    profile.load(target)
    return target


def ticket(root, oid, target, baseline):
    item = load(root, oid)
    target = development_checkout(target)
    if not baseline.strip():
        raise FactoryError("record the replay result or baseline measurement before opening a ticket")
    cfg = profile.load(target)["tracker"]
    slug = re.sub(r"[^a-z0-9]+", "-", item["summary"].lower()).strip("-")[:45].rstrip("-")
    effort = f"eval-{slug or 'improvement'}-{oid}"
    folder = target / cfg["root"] / effort
    if cfg.get("layout") != "flat":
        folder /= "issues"
    folder = folder.resolve()
    if not folder.is_relative_to(target):
        raise FactoryError("the tracker must be inside the development checkout")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "01-improvement.md"
    statuses = cfg.get("status", {})
    pending = statuses.get("plan_review", "needs-plan-review")
    text = (f"# 01 - {item['summary']}\n\nType: task\nStatus: {pending}\nPlan-Approval: pending\nBlocked by: -\n\n"
            f"## Outcome\n\n{item['expected']}\n\n"
            f"## Acceptance\n\n- {item['expected']}\n\n"
            f"## Proof\n\n{item['check']}\n\nBaseline: {baseline.strip()}\n\n"
            f"## Observation\n\n{item['observed']}\n\nEvaluation: {oid}\n")
    try:
        with path.open("x") as handle:
            handle.write(text)
    except FileExistsError:
        pass
    return path

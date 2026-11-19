"""Resolve unmerged dependencies to reviewed commits and track when those deliveries change."""
from pathlib import Path

from . import tracker as T
from .util import git, git_ok


def rejected_base(run, tickets, latest, statuses):
    for path, dependency in run.get("stacked_on", {}).items():
        ticket = tickets.get(path)
        if (ticket is None or ticket.status not in {*statuses["done"], statuses["ready"]} or
                latest.get(path, {}).get("id") != dependency):
            return path
    return None


def plan(root, ticket, tickets, latest, statuses):
    """Return the latest reviewed branch that contains every unmerged blocker in each repo."""
    lineage, heads = {}, {}
    blockers = T.blockers(ticket, T.references(tickets.values())) if ticket.blocked_by else ()
    for base_ticket in blockers:
        if base_ticket is None:
            return None
        if base_ticket.status in statuses["done"]:
            continue
        delivery = latest.get(base_ticket.path, {})
        if delivery.get("outcome") != "delivered" or rejected_base(delivery, tickets, latest, statuses):
            return None
        lineage.update(delivery.get("stacked_on", {}))
        lineage[base_ticket.path] = delivery["id"]
    for path in lineage:
        if tickets[path].status in statuses["done"]:
            continue
        delivery = latest[path]
        for name, reviewed in delivery.get("reviewed_heads", {}).items():
            repo = Path(root) / name
            branch = delivery["branch"]
            tip = git(repo, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)
            # A subsequent edit of the branch needs review before another ticket can start from it.
            if not tip or tip != git(repo, "rev-parse", "--verify", reviewed, check=False):
                return None
            if tip != git(repo, "rev-parse", "--verify", delivery["base"][name], check=False):
                heads.setdefault(name, []).append({"branch": branch, "head": tip, "ticket": path})
    bases = {}
    for name, candidates in heads.items():
        repo = Path(root) / name
        base = next((candidate for candidate in reversed(candidates) if all(
            git_ok(repo, "merge-base", "--is-ancestor", other["head"], candidate["head"])
            for other in candidates)), None)
        if base is None:
            return None
        bases[name] = base
    return {"stacked_on": lineage, "stack_bases": bases}

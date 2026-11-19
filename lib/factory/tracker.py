"""Markdown tickets in one directory per effort, with a nested issues/ layout for existing projects."""
import datetime
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import FactoryError, atomic_write_text, sha256_file

NAME_RE = re.compile(r"^(\d+[a-z]?)-.+\.md$")
PRIORITY = {"high": 0, "normal": 1, "low": 2}


def header(text, key):
    """Value of a 'Key: value' or '**Key:** value' line near the top, else None."""
    for line in text.splitlines()[:40]:
        plain = line.strip().replace("**", "")
        if plain.lower().startswith(key.lower() + ":"):
            return plain.split(":", 1)[1].strip()
    return None


def first_word(value):
    return re.split(r"[\s,(]", value.strip(), maxsplit=1)[0].lower() if value else ""


@dataclass
class Ticket:
    path: str          # relative to the repo root
    effort: str
    number: str
    title: str
    type: str
    status: str
    blocked_by: list = field(default_factory=list)
    contract: str | None = None
    priority: str = "normal"
    revision: str = ""
    approval: str | None = None
    plan_sha: str = ""

    @property
    def ref(self):
        return f"{self.effort}/{self.number}"


def _number_key(number):
    m = re.match(r"(\d+)([a-z]?)", number)
    return (int(m.group(1)), m.group(2)) if m else (10**6, number)


def plan_sha(text):
    fields = {"status", "plan-approval"}
    plan, comments = [], False
    for number, line in enumerate(text.splitlines()):
        if line.startswith("## "):
            comments = line[3:].strip().lower() == "comments"
        field = line.strip().replace("**", "").partition(":")[0].lower()
        if number < 40 and ":" in line and field in fields:
            fields.remove(field)
        elif not comments:
            plan.append(line)
    return hashlib.sha256("\n".join(plan).rstrip().encode()).hexdigest()


def plan_revision(ticket, contract):
    return hashlib.sha256(f"{ticket.plan_sha}\0{contract or ''}".encode()).hexdigest()


def awaiting_plan(ticket, cfg):
    status = cfg["status"]
    if ticket.status in (status["plan_review"], status["plan_changes"]):
        return True
    required = cfg.get("require_plan_review") or ticket.approval is not None
    return bool(required and ticket.approval != plan_revision(ticket, ticket.contract))


def load(root, cfg):
    base = Path(root) / cfg["root"]
    tickets = []
    for effort in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")) if base.is_dir() else []:
        directory = effort if cfg.get("layout") == "flat" else effort / "issues"
        for f in sorted(directory.glob("*.md")):
            m = NAME_RE.match(f.name)
            if not m:
                continue
            contents = f.read_bytes()
            text = contents.decode("utf-8", errors="replace")
            title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), f.stem)
            blocked = header(text, "Blocked by") or ""
            tickets.append(Ticket(
                path=str(f.relative_to(root)), effort=effort.name, number=m.group(1), title=title,
                type=first_word(header(text, "Type")), status=first_word(header(text, "Status")),
                contract=header(text, "Contract"),
                priority=first_word(header(text, "Priority")) or "normal", revision=hashlib.sha256(contents).hexdigest(),
                approval=header(text, "Plan-Approval"), plan_sha=plan_sha(text),
                blocked_by=re.findall(r"\b\d+[a-z]?\b", blocked)))
    return tickets


def contract_revision(root, cfg, effort):
    path = Path(root) / cfg["root"] / effort / "contract.md"
    return sha256_file(path) if path.is_file() else None


def contract_issues(root, cfg, tickets):
    """Hold the entire effort until every unfinished build ticket reflects its current contract."""
    issues, revisions = {}, {}
    for ticket in tickets:
        if ticket.type not in cfg["build_types"] or ticket.status in cfg["status"]["done"]:
            continue
        if ticket.effort not in revisions:
            revisions[ticket.effort] = contract_revision(root, cfg, ticket.effort)
        if ticket.contract != revisions[ticket.effort]:
            issues.setdefault(ticket.effort, []).append(ticket.ref)
    return issues


def references(tickets):
    refs = {}
    for ticket in tickets:
        refs.setdefault((ticket.effort, _number_key(ticket.number)), []).append(ticket)
    return refs


def blockers(ticket, refs):
    matches = [refs.get((ticket.effort, _number_key(number)), []) for number in ticket.blocked_by]
    return [group[0] if len(group) == 1 else None for group in matches]


def dependency_issues(tickets, cfg):
    refs = references(tickets)
    for group in refs.values():
        if len(group) > 1:
            yield f"{group[0].ref}: duplicate ticket number in " + ", ".join(t.path for t in group)
    for ticket in tickets:
        if ticket.status in cfg["status"]["queue"] and ticket.type in cfg["build_types"]:
            for number in ticket.blocked_by:
                matches = refs.get((ticket.effort, _number_key(number)), [])
                if not matches:
                    yield f"{ticket.ref}: missing dependency {ticket.effort}/{number}"
                elif len(matches) > 1:
                    yield f"{ticket.ref}: ambiguous dependency {ticket.effort}/{number}"


def frontier(root, cfg, *, tickets=None, include_delivered=False):
    """Open, unblocked, unclaimed build tickets, lowest number first within each effort."""
    tickets = load(root, cfg) if tickets is None else tickets
    status = cfg["status"]
    done = set(status["done"])
    if include_delivered:
        done.add(status["ready"])
    stale = contract_issues(root, cfg, tickets)
    refs = references(tickets)
    out = []
    for t in tickets:
        if (t.effort in stale or t.status not in status["queue"] or t.type not in cfg["build_types"] or
                awaiting_plan(t, cfg)):
            continue
        if len(refs[t.effort, _number_key(t.number)]) == 1 and all(
                b is not None and b.status in done for b in blockers(t, refs)):
            out.append(t)
    return sorted(out, key=lambda t: (PRIORITY.get(t.priority, PRIORITY["normal"]), t.effort, _number_key(t.number)))


def find(root, cfg, ref_or_path):
    tickets = load(root, cfg)
    matches = [t for t in tickets if ref_or_path in (t.path, t.ref)]
    if not matches:
        matches = [t for t in tickets if t.path.endswith("/" + ref_or_path)]
    if len(matches) > 1:
        raise FactoryError(f"ambiguous ticket {ref_or_path}: " + ", ".join(t.path for t in matches))
    return matches[0] if matches else None


def field_text(text, key, new):
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    for i, line in enumerate(lines[:40]):
        if line.strip().replace("**", "").lower().startswith(key.lower() + ":"):
            prefix = f"**{key}:** " if line.lstrip().startswith("**") else f"{key}: "
            lines[i] = prefix + new + newline
            break
    else:
        lines.insert(1, f"{key}: {new}{newline}")
    return "".join(lines)


def status_text(text, new):
    return field_text(text, "Status", new)


def set_status(root, path, new, *, expected=None):
    f = (Path(root) / path).resolve()
    contents = f.read_bytes()
    if expected is None or hashlib.sha256(contents).hexdigest() == expected:
        atomic_write_text(f, status_text(contents.decode("utf-8"), new))


def comment(root, path, text, who="factory"):
    f = (Path(root) / path).resolve()
    contents = f.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in contents else "\n"
    body = contents.rstrip("\r\n")
    if "\n## Comments" not in "\n" + body:
        body += newline * 2 + "## Comments" + newline
    stamp = datetime.date.today().isoformat()
    lines = text.strip().splitlines()
    entry = f"- {who}, {stamp}: {lines[0]}" + "".join(f"{newline}  {line}" for line in lines[1:])
    atomic_write_text(f, body + newline * 2 + entry + newline)


def human_comments_since_factory(root, path):
    """Comment entries written after the factory's last comment and not by the factory."""
    text = (Path(root) / path).read_text()
    if "## Comments" not in text:
        return []
    section = text.split("## Comments", 1)[1]
    entries = re.split(r"\n(?=- )", "\n" + section)
    entries = [e.strip() for e in entries if e.strip().startswith("- ")]
    last_factory = max((i for i, e in enumerate(entries) if e.startswith("- factory")), default=-1)
    return [e for e in entries[last_factory + 1:] if not e.startswith("- factory")]

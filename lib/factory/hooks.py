"""Hook handlers. They act only on factory agents (agent_type 'factory:<role>'), never on normal sessions."""
import json
import re
from pathlib import Path

from .util import PLUGIN_ROOT, factory_dir, find_root, now, read_json

READ_ONLY = {"researcher", "reviewer", "security", "ui-tester", "learner"}
HOOK_LOG_LIMIT = 1024 * 1024


def _role(inp):
    agent_type = inp.get("agent_type") or ""
    return agent_type.split(":", 1)[1] if agent_type.startswith("factory:") else None


def _log(root, inp, note):
    try:
        path = factory_dir(root) / "hooks.log"
        if path.is_file() and path.stat().st_size >= HOOK_LOG_LIMIT:
            path.replace(path.with_name("hooks.log.1"))
        with path.open("a") as f:
            f.write(json.dumps({"t": now(), "event": inp.get("hook_event_name"), "agent_type": inp.get("agent_type"),
                                "tool": inp.get("tool_name"), "note": note}) + "\n")
    except OSError:
        pass


HEADER = re.compile(r"FACTORY RUN ([\w.-]+) RESULT ([\w.-]+) SPAWN (\d+)")


def _spawn_header(inp):
    """(run id, stem, spawn) from the spawn prompt, the first user message of the agent's transcript."""
    path = inp.get("agent_transcript_path")
    if not path:
        return None
    try:
        with open(path) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("type") != "user":
                    continue
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                m = HEADER.search(content or "")
                if not m or ".." in m.group(1) or ".." in m.group(2):
                    return None
                return m.group(1), m.group(2), int(m.group(3))
    except (OSError, ValueError):
        return None
    return None


def subagent_stop(inp):
    """Store a factory agent's final message as the result of the spawn its transcript names; send it back once if
    the VERDICT line is missing. Never writes run.json: the engine is its only writer."""
    role = _role(inp)
    if not role:
        return None
    from . import engine as E
    root = find_root(inp.get("cwd"))
    head = _spawn_header(inp)
    if not head:
        _log(root, inp, "unattributable: no FACTORY RUN header in the agent transcript; nothing stored")
        return None
    rid, stem, n = head
    if not factory_dir(root).is_dir():
        return None
    with E.state_lock(root):
        run = read_json(factory_dir(root) / "runs" / rid / "run.json")
        if not run or run.get("spawn_ids", {}).get(stem) != n or stem not in run.get("pending", {}).values():
            _log(root, inp, f"stale spawn {stem}#{n} of run {rid}; nothing stored")
            return None
        msg = inp.get("last_assistant_message") or ""
        if not re.match(r"\s*VERDICT:\s*[A-Za-z-]+", msg) and not inp.get("stop_hook_active"):
            _log(root, inp, f"blocked {stem}#{n}: no VERDICT line")
            return {"decision": "block",
                    "reason": "Your final message must start with the line 'VERDICT: <value>' defined in your instructions, "
                              "followed by the sections they require. Send the complete result again as your final message."}
        E.store_result(root, rid, stem, n, msg, "hook", transcript=inp.get("agent_transcript_path"))
    _log(root, inp, f"stored {stem}#{n}")
    return None


def _under(path, base):
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


GIT_PUSH = re.compile(r"\bgit(\s+-[Cc]\s+\S+|\s+--?[\w-]+(=\S+)?)*\s+push\b")   # not 'git stash push'
FACTORY_STATE = r"\.factory/(profile\.json|state\.json|learn\.json|runs/)"


def _beat(root):
    """Mark that a factory agent is working; the engine waits for agents as long as this keeps changing."""
    beat = factory_dir(root) / "beat"
    if beat.parent.is_dir():
        try:
            beat.touch()
        except OSError:
            pass


def guard(inp):
    """Deny pushes, writes to .factory/, writes by read-only roles, and factory edits outside the learner's paths."""
    role = _role(inp)
    if not role:
        return None
    tool, ti = inp.get("tool_name", ""), inp.get("tool_input") or {}
    root = find_root(inp.get("cwd"))
    _beat(root)
    deny = None
    if tool == "Bash":
        cmd = ti.get("command", "")
        if GIT_PUSH.search(cmd):
            deny = "Delivery is local only: factory agents never push."
        elif "--no-verify" in cmd:
            deny = "Hooks are not skipped in the factory."
        elif re.search(r">\s*['\"]?[^\s|;&<>'\"]*" + FACTORY_STATE, cmd) or (re.search(FACTORY_STATE, cmd) and \
                re.search(r"(\bsed\s+-i|\brm\s|\bmv\s|\bcp\s|\btee\s|\btruncate\s)", cmd)):
            deny = "Only the factory scripts write to .factory/."
    elif tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        target = Path(ti.get("file_path") or ti.get("notebook_path") or "").resolve()
        if role in READ_ONLY:
            deny = f"The {role} is read-only."
        elif _under(target, (Path(root) / ".factory").resolve()):
            deny = "Only the factory scripts write to .factory/."
        elif _under(target, PLUGIN_ROOT):
            deny = "Factory agents may edit only the project they are building."
    if deny:
        _log(root, inp, "denied: " + deny)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": deny}}
    return None

"""Small helpers shared by every factory module. Standard library only."""
import datetime
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
FACTORY_BIN = PLUGIN_ROOT / "bin" / "factory"


class FactoryError(Exception):
    """A refusal the caller should show as is."""


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def atomic_write_text(path, text):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                     suffix=".tmp", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            try:
                tmp.chmod(stat.S_IMODE(path.stat().st_mode))
            except FileNotFoundError:
                pass
            handle.write(text)
            handle.close()
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def git(repo, *args, check=True, strip=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise FactoryError(f"git {' '.join(args)} in {repo}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.rstrip() if strip else r.stdout    # porcelain status depends on leading spaces


# Files Claude Code's sandbox mounts into the working directory while a sandboxed session runs.
SANDBOX_PLACEHOLDERS = {".bash_profile", ".bashrc", ".gitconfig", ".gitmodules", ".mcp.json", ".profile",
                        ".ripgreprc", ".vscode", ".zprofile", ".zshrc", ".idea", ".claude", ".claude/"}


def status_paths(repo, *, check=True):
    entries = iter(git(repo, "status", "--porcelain", "-z", "--untracked-files=all", "--ignore-submodules=all",
                       check=check).split("\0"))
    for entry in entries:
        if entry:
            code = entry[:2]
            yield code, entry[3:]
            if "R" in code or "C" in code:
                yield code, next(entries)


def dirty_paths(repo, ignore_prefixes=(), *, check=True):
    """Changed tracked files and untracked files, minus sandbox placeholders and ignored prefixes."""
    out = []
    for code, path in status_paths(repo, check=check):
        if code == "??" and path.rstrip("/").split("/")[0] in SANDBOX_PLACEHOLDERS:
            continue
        if any(path.rstrip("/") == p.rstrip("/") or path.startswith(p.rstrip("/") + "/") for p in ignore_prefixes):
            continue
        out.append(path)
    return out


def git_ok(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).returncode == 0


def find_root(start=None):
    """The directory that holds .factory/, else the outermost git work tree around start."""
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    for d in [start, *start.parents]:
        if (d / ".factory").is_dir():
            return d
    top = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-superproject-working-tree"],
                         capture_output=True, text=True).stdout.strip()
    if top:
        return Path(top)
    top = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    return Path(top) if top else start


def factory_dir(root):
    return Path(root) / ".factory"


def factory_sha():
    r = subprocess.run(["git", "-C", str(PLUGIN_ROOT), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "uncommitted"

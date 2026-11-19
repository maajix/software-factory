"""Deterministic first pass of /factory:init: everything a script can read without judgment."""
import collections
import configparser
import json
import re
import shutil
import subprocess
from pathlib import Path

from .util import dirty_paths, git, git_ok

GATE_SCRIPT = re.compile(r"^(test|lint|typecheck|format|build|check|audit)\b|:check$")


def submodules(root):
    f = Path(root) / ".gitmodules"
    if not f.exists():
        return []
    cp = configparser.ConfigParser()
    cp.read_string(f.read_text())
    out = []
    for sec in cp.sections():
        if sec.startswith("submodule"):
            d = cp[sec]
            out.append({"name": sec.split('"')[1] if '"' in sec else sec, "path": d.get("path"),
                        "url": d.get("url", ""), "branch": d.get("branch")})
    return out


def host_of(url):
    for host in ("bitbucket.org", "github.com", "gitlab.com"):
        if host in url:
            return host.split(".")[0]
    return "unknown"


def ci_commands(repo):
    """Script lines of bitbucket-pipelines.yml / GitHub workflows, without a YAML parser."""
    lines = []
    files = [repo / "bitbucket-pipelines.yml", *sorted((repo / ".github" / "workflows").glob("*.y*ml"))]
    for f in files:
        if not f.exists():
            continue
        in_script = None
        in_block = None
        for raw in f.read_text(errors="replace").splitlines():
            stripped = raw.strip()
            indent = len(raw) - len(raw.lstrip())
            if in_block is not None:
                if not stripped or indent > in_block:
                    continue
                in_block = None
            if re.match(r"^(?:-\s+)?run:\s*[|>](?:[+-]?[1-9]?|[1-9][+-]?)\s*(?:#.*)?$", stripped):
                in_block = indent
                in_script = None
                continue
            if re.match(r"^(?:script|run):\s*$", stripped):
                in_script = indent
                continue
            m = re.match(r"^(?:-\s+)?run:\s*(\S.*)$", stripped)
            if m:
                lines.append(m.group(1))
                continue
            if in_script is not None:
                if stripped and indent <= in_script:
                    in_script = None
                elif stripped.startswith("- "):
                    lines.append(stripped[2:].strip().strip("'\""))
    return [l for l in lines if l]


def repo_facts(root, rel):
    repo = Path(root) / rel
    facts = {"path": rel, "manifests": [], "scripts": {}, "package_manager": None, "ci": []}
    pkg = repo / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text())
        facts["manifests"].append("package.json")
        facts["scripts"] = {k: v for k, v in data.get("scripts", {}).items() if GATE_SCRIPT.search(k)}
        pm = data.get("packageManager", "")
        facts["package_manager"] = pm.split("@")[0] if pm else (
            "pnpm" if (repo / "pnpm-lock.yaml").exists() else "npm")
        facts["node_engine"] = data.get("engines", {}).get("node")
        facts["has_node_modules"] = (repo / "node_modules").is_dir()
    py = repo / "pyproject.toml"
    if py.exists():
        text = py.read_text()
        facts["manifests"].append("pyproject.toml")
        facts["package_manager"] = facts["package_manager"] or ("uv" if (repo / "uv.lock").exists() else "pip")
        facts["python_tools"] = [t for t in ("pytest", "ruff", "mypy", "black") if t in text]
        facts["has_venv"] = (repo / ".venv").is_dir()
    for name in ("Makefile", "Dockerfile", "docker-compose.yml", "pnpm-lock.yaml", "uv.lock"):
        if (repo / name).exists():
            facts["manifests"].append(name)
    facts["ci"] = ci_commands(repo)
    facts["context_files"] = [p.name for p in (repo / "CLAUDE.md", repo / "AGENTS.md") if p.exists()]
    facts["test_dirs"] = sorted({str(p.relative_to(repo)).split("/")[0] + "/" + p.name
                                 for p in repo.glob("*/test*") if p.is_dir()} |
                                {p.name for p in repo.glob("test*") if p.is_dir()} |
                                {p.name for p in repo.glob("__tests__") if p.is_dir()})[:10]
    return facts


def commit_conventions(repos_paths, limit=400):
    prefixes, merges, total = collections.Counter(), collections.Counter(), 0
    for repo in repos_paths:
        for s in git(repo, "log", f"-{limit}", "--format=%s", check=False).splitlines():
            total += 1
            m = re.match(r"^([A-Za-z]+):\s", s)
            if m:
                prefixes[m.group(1)] += 1
            m = re.match(r"^Merged in ([\w./-]+)|^Merge branch '([\w./-]+)'", s)
            if m:
                name = m.group(1) or m.group(2)
                merges[name.split("-")[0] if "/" in name else name.split("/")[0]] += 1
    return {"subjects_sampled": total, "prefixes": prefixes.most_common(12),
            "merged_branch_prefixes": merges.most_common(12)}


def tracker_facts(root):
    from .tracker import load
    native = {"root": "docs/work", "layout": "flat"}
    legacy = {"root": "docs/issues"}
    cfg = native if (Path(root) / native["root"]).is_dir() else legacy
    if not (Path(root) / cfg["root"]).is_dir():
        return None
    tickets = load(root, cfg)
    return {"type": "markdown", **cfg, "tickets": len(tickets),
            "efforts": sorted({t.effort for t in tickets}),
            "statuses": collections.Counter(t.status for t in tickets).most_common(),
            "types": collections.Counter(t.type for t in tickets).most_common(),
            "agent_docs": [str(p.relative_to(root)) for p in (Path(root) / "docs" / "agents").glob("*.md")]}


def detect(root):
    root = Path(root)
    subs = submodules(root)
    rels = ["."] + [s["path"] for s in subs if s["path"] and (root / s["path"] / ".git").exists()]
    origin = git(root, "remote", "get-url", "origin", check=False)
    tools = {t: bool(shutil.which(t)) for t in ("git", "node", "pnpm", "npm", "uv", "python3", "docker",
                                                  "redis-server", "rg", "agent-browser", "playwright")}
    docker_up = tools["docker"] and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    return {
        "root": str(root),
        "origin_host": host_of(origin),
        "submodules": [{**s, "host": host_of(s["url"]), "checked_out": s["path"] in rels} for s in subs],
        "repos": [repo_facts(root, r) for r in rels],
        "conventions": commit_conventions([root / r for r in rels]),
        "tracker": tracker_facts(root),
        "env_examples": [str(p.relative_to(root)) for p in root.glob("**/.env.example")
                         if "node_modules" not in p.parts][:20],
        "compose_files": [p.name for p in root.glob("docker-compose*.yml")],
        "tools": {**tools, "docker_daemon": docker_up},
        "dirty": {r: dirty_paths(root / r)[:10] for r in rels},
    }

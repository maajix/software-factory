"""Deterministic gates: run profile commands, parse runner summaries, check conventions on a diff."""
import fnmatch
import ipaddress
import re
import shutil
import subprocess
import time
from pathlib import Path

from .util import dirty_paths, git, git_ok

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# Summary lines of the runners the example project uses. Counts are summed over every summary line found,
# because composite scripts (test:system) print one summary per runner invocation.
SUMMARY_LINES = [
    re.compile(r"^\s*Tests:?\s+(?P<body>.*\d+\s+(passed|failed).*)$"),           # vitest, jest
    re.compile(r"^=*\s*(?P<body>(\d+\s+\w+,?\s*)+)\s+in\s+[\d.]+\s*s\b.*$"),        # pytest
]


UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in ")
UNITTEST_FAILED = re.compile(r"^FAILED \((.*)\)")


def parse_summary(output):
    """{'passed','failed','errors'} summed over all runner summary lines, or None if none found."""
    counts, found = {"passed": 0, "failed": 0, "errors": 0}, False
    lines = ANSI.sub("", output).splitlines()
    for i, line in enumerate(lines):          # python unittest: "Ran N tests" then "OK" or "FAILED (failures=1)"
        m = UNITTEST_RAN.match(line)
        if m:
            ran, found = int(m.group(1)), True
            bad = {"failures": 0, "errors": 0}
            for later in lines[i + 1:i + 4]:
                f = UNITTEST_FAILED.match(later)
                if f:
                    for k, v in re.findall(r"(failures|errors)=(\d+)", f.group(1)):
                        bad[k] = int(v)
            counts["failed"] += bad["failures"]
            counts["errors"] += bad["errors"]
            counts["passed"] += ran - bad["failures"] - bad["errors"]
    for line in lines:
        for rx in SUMMARY_LINES:
            m = rx.match(line)
            if not m:
                continue
            body = m.group("body")
            for key, words in (("passed", "passed"), ("failed", "failed"), ("errors", "errors?")):
                n = re.search(rf"(\d+)\s+{words}\b", body)
                if n:
                    counts[key] += int(n.group(1))
                    found = True
            break
    return counts if found else None


def missing_requirements(requires):
    missing = []
    for req in requires or []:
        if req == "docker":
            if not shutil.which("docker") or subprocess.run(
                    ["docker", "info"], capture_output=True, timeout=20).returncode:
                missing.append("docker (daemon not reachable)")
        elif not shutil.which(req):
            missing.append(req)
    return missing


def run_gate(root, gate, log_path, timeout=None):
    """Run one gate command without a pipe; the verdict uses the exit code and the parsed summary."""
    missing = missing_requirements(gate.get("requires"))
    base = {"id": gate["id"], "cmd": gate["cmd"], "repo": gate["repo"]}
    if missing:
        return {**base, "status": "skipped", "ok": None, "reason": "missing: " + ", ".join(missing)}
    start = time.time()
    try:
        r = subprocess.run(gate["cmd"], shell=True, cwd=Path(root) / gate["repo"], capture_output=True,
                           text=True, timeout=timeout or gate.get("timeout", 1800))
        out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
    except subprocess.TimeoutExpired as e:
        out, code = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    Path(log_path).write_text(out)
    counts = parse_summary(out)
    ok = code == 0
    if gate.get("expect_tests") and ok:
        ok = bool(counts) and counts["passed"] > 0 and counts["failed"] == 0 and counts["errors"] == 0
    tail = "\n".join(ANSI.sub("", out).rstrip().splitlines()[-40:])
    return {**base, "status": "pass" if ok else "fail", "ok": ok, "exit": code, "counts": counts,
            "seconds": round(time.time() - start, 1), "log": str(log_path), "tail": tail}


# ---- convention checks on the run's branch -------------------------------------------------------

ALLOWED_NETS = [ipaddress.ip_network(n) for n in (
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "127.0.0.0/8", "0.0.0.0/32", "255.255.255.255/32", "169.254.0.0/16", "224.0.0.0/4")]
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
EMAIL = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+[A-Za-z]{2,})")
SAFE_MAIL_DOMAINS = ("example.com", "example.org", "example.net", ".test", ".invalid", ".localhost", ".example")
SKIP_FILES = ("pnpm-lock.yaml", "package-lock.json", "uv.lock", "yarn.lock", ".svg", ".png", ".jpg", ".pdf")


def tenant_data_hits(diff_text, allow=()):
    """Added lines that carry a public IPv4 or a real-looking e-mail address."""
    hits, current = [], None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
            continue
        if not current or current.endswith(SKIP_FILES) or not line.startswith("+") or line.startswith("+++"):
            continue
        for ip in IPV4.findall(line):
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if ip not in allow and not any(addr in n for n in ALLOWED_NETS):
                hits.append(f"{current}: public IP {ip}")
        for m in EMAIL.finditer(line):
            domain = m.group(1).lower()
            if m.group(0) not in allow and not domain.endswith(SAFE_MAIL_DOMAINS) and domain not in SAFE_MAIL_DOMAINS:
                hits.append(f"{current}: e-mail address at {domain}")
    return hits


def check_conventions(root, profile, run, repos):
    """List of failure strings for the touched repos; empty means the conventions hold."""
    conv, problems = profile.get("conventions", {}), []
    tracker_root = profile.get("tracker", {}).get("root", "docs/issues")
    branch_rx = re.compile(conv["branch_regex"]) if conv.get("branch_regex") else None
    commit_rx = re.compile(conv["commit_regex"]) if conv.get("commit_regex") else None
    for name in repos:
        repo = Path(root) / name
        base = run["base"][name]
        branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if branch != run["branch"]:
            problems.append(f"{name}: on branch {branch}, expected {run['branch']}")
        if branch_rx and not branch_rx.match(run["branch"]):
            problems.append(f"{name}: branch name {run['branch']} does not match {conv['branch_regex']}")
        dirty = dirty_paths(repo, (tracker_root, ".factory") if name == "." else ())
        if dirty:
            problems.append(f"{name}: uncommitted changes left: {', '.join(dirty[:8])}")
        for subject in git(repo, "log", "--format=%s", f"{base}..HEAD").splitlines():
            if commit_rx and not commit_rx.match(subject):
                problems.append(f"{name}: commit subject '{subject}' does not match {conv['commit_regex']}")
        raw = git(repo, "diff", "--raw", f"{base}..HEAD")
        for line in raw.splitlines():
            parts = line.split("\t")
            meta, path = parts[0], parts[-1]
            if "160000" in meta.lstrip(":").split()[:2]:
                problems.append(f"{name}: changes the submodule pointer {path} (never commit submodule pointers)")
            if any(fnmatch.fnmatch(path, pat) for pat in conv.get("forbidden_paths", [])):
                problems.append(f"{name}: changes the protected file {path}")
        diff = git(repo, "diff", "-U0", f"{base}..HEAD")
        for hit in tenant_data_hits(diff, profile.get("tenant_data_allow", [])):
            problems.append(f"{name}: possible tenant data, {hit}")
    return problems


def touched_repos(root, profile, run):
    """Repos whose run branch has commits beyond its recorded base."""
    out = []
    for name, base in run.get("base", {}).items():
        repo = Path(root) / name
        if git_ok(repo, "rev-parse", "--verify", run["branch"]) and git(repo, "rev-list", "--count", f"{base}..{run['branch']}") != "0":
            out.append(name)
    return out


def changed_files(root, run, name, head=None):
    return git(Path(root) / name, "diff", "--name-only", f"{run['base'][name]}..{head or run['branch']}").splitlines()


def gates_for(profile, repo, files):
    """Fast gates always; slow gates only when a changed file matches one of their path globs."""
    out = []
    for g in profile["gates"]:
        if g["repo"] != repo or g.get("disabled"):
            continue
        if g.get("tier", "fast") == "fast" or any(fnmatch.fnmatch(f, p) for f in files for p in g.get("paths", ["*"])):
            out.append(g)
    return out

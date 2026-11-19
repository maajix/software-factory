"""The project profile written by /factory:init and read by every script."""
from pathlib import Path

from .gates import run_gate
from .util import FactoryError, factory_dir, now, read_json, sha256_file, write_json

REQUIRED = ("repos", "gates", "tracker", "conventions")


def path(root):
    return factory_dir(root) / "profile.json"


def load(root):
    prof = read_json(path(root))
    if prof is None:
        raise FactoryError("No .factory/profile.json. Run /factory:init first.")
    missing = [k for k in REQUIRED if k not in prof]
    if missing:
        raise FactoryError(f"profile.json lacks {', '.join(missing)}; rerun /factory:init.")
    return prof


def sha(root):
    return sha256_file(path(root))


def input_hashes(root, prof):
    out = {}
    for rel in prof.get("inputs", {}):
        p = Path(root) / rel
        out[rel] = sha256_file(p) if p.exists() else None
    return out


def gate_inputs(gate, hashes):
    """The inputs that can change a gate: those in its repo and those at the root."""
    if not hashes or gate.get("repo") in (None, "", "."):
        return hashes
    return {k: v for k, v in hashes.items() if "/" not in k or k.startswith(gate["repo"].rstrip("/") + "/")}


def drift(root, prof):
    """Enabled gates whose baseline was verified against other contents of their own inputs than today's, or never
    verified. Each gate carries its own input hashes because init verifies gate by gate."""
    if not prof.get("inputs"):
        return []
    now_hashes = input_hashes(root, prof)
    return [g["id"] for g in prof["gates"]
            if not g.get("disabled") and gate_inputs(g, (g.get("baseline") or {}).get("inputs"))
            != gate_inputs(g, now_hashes)]


def verify(root, only=None, setup=True, setup_only=False):
    """Run setup commands, then every gate on the current checkout; store results as baselines."""
    prof = load(root)
    logs = factory_dir(root) / "verify"
    report = []
    if setup:
        for step in prof.get("setup", []):
            res = run_gate(root, {"id": step["id"], "cmd": step["cmd"], "repo": step["repo"],
                                  "requires": step.get("requires"), "timeout": step.get("timeout", 1800)},
                           logs / f"setup-{step['id'].replace(':', '_')}.log")
            report.append({**res, "kind": "setup"})
    for gate in [] if setup_only else prof["gates"]:
        if (only and gate["id"] not in only) or (not only and gate.get("disabled")):
            continue
        res = run_gate(root, gate, logs / f"{gate['id'].replace(':', '_')}.log")
        old = gate.get("baseline") or {}
        gate["baseline"] = {"status": res["status"], "counts": res.get("counts"), "seconds": res.get("seconds"),
                            "reason": res.get("reason"), "verified_at": now(),
                            # a failed gate keeps its old inputs, so changed inputs stay flagged until it passes
                            "inputs": input_hashes(root, prof) if res["status"] in ("pass", "skipped") else old.get("inputs")}
        report.append({**res, "kind": "gate"})
    prof["inputs"] = input_hashes(root, prof) if prof.get("inputs") else prof.get("inputs", {})
    write_json(path(root), prof)
    for res in report:
        if res["status"] == "pass" and res.get("log"):
            Path(res.pop("log")).unlink(missing_ok=True)
    if logs.is_dir() and not any(logs.iterdir()):
        logs.rmdir()
    return report

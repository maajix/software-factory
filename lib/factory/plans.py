"""Open finished issue plans in Plannotator and record the approved revisions."""
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import engine as E
from . import profile as P
from . import tracker as T
from .util import FactoryError, atomic_write_text, read_json


def review(root, name):
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="factory-plan-review-") as directory:
        stage = Path(directory)
        with E.state_lock(root):
            profile = P.sha(root)
            cfg = E.tracker_cfg(P.load(root))
            issue = T.find(root, cfg, name)
            candidates = [issue] if issue else [t for t in T.load(root, cfg) if t.effort == name]
            states = cfg["status"]
            ready = {*states["queue"], states["plan_review"], states["plan_changes"]}
            tickets = [t for t in candidates if t.type in cfg["build_types"] and t.status in ready and T.awaiting_plan(t, cfg)]
            if not tickets:
                raise FactoryError(f"No finished issue plans waiting for approval for {name}.")
            active = E.state(root).get("active")
            if active and any(t.path == E.load_run(root, active).get("ticket") for t in tickets):
                raise FactoryError("The plan belongs to an active run. Finish that run before reopening it for plan review.")
            shared = Path(cfg["root"]) / tickets[0].effort / "contract.md"
            contract = T.contract_revision(root, cfg, tickets[0].effort)
            if any(t.contract != contract for t in tickets):
                raise FactoryError("Reconcile the tickets with the current feature contract before plan review.")
            snapshots = {}
            for path in ([shared] if contract else []) + [Path(t.path) for t in tickets]:
                source = (root / path).resolve()
                if not source.is_relative_to(root):
                    raise FactoryError(f"The plan file is outside the project: {path}.")
                data = source.read_bytes()
                snapshots[path] = data
                target = stage / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if any(hashlib.sha256(snapshots[Path(t.path)]).hexdigest() != t.revision for t in tickets):
                raise FactoryError("A ticket changed while preparing its review. Retry factory plan-review.")
            if contract and T.contract_revision(stage, cfg, tickets[0].effort) != contract:
                raise FactoryError("The feature contract changed while preparing its review. Retry factory plan-review.")
        binary = shutil.which("plannotator")
        if not binary:
            raise FactoryError("Plannotator is required for plan approval. Install its CLI and retry factory plan-review.")
        result_path = stage / "decision.json"
        try:
            completed = subprocess.run(
                [binary, "annotate", *[str(stage / path) for path in snapshots],
                 "--gate", "--json", "--require-approval", "--result-file", str(result_path)],
                cwd=root, stdout=subprocess.PIPE, text=True)
        except OSError as e:
            raise FactoryError(f"Could not start Plannotator: {e}") from e
        try:
            result = read_json(result_path)
        except ValueError as e:
            raise FactoryError("Plannotator returned an invalid review result.") from e
        decision = result.get("decision") if isinstance(result, dict) else None
        if (completed.returncode, decision) not in {(0, "approved"), (1, "annotated"), (1, "dismissed")}:
            raise FactoryError("Plannotator did not complete the review. Retry factory plan-review.")
        with E.state_lock(root):
            if (P.sha(root) != profile or T.contract_revision(root, cfg, tickets[0].effort) != contract or
                    any(not (root / path).is_file() or (root / path).read_bytes() != data
                        for path, data in snapshots.items())):
                raise FactoryError("Plans changed during review. Open the updated files for approval.")
            active = E.state(root).get("active")
            if active and any(t.path == E.load_run(root, active).get("ticket") for t in tickets):
                raise FactoryError("An issue entered an active run during review. Finish it before changing its plan.")
            for ticket in tickets:
                if decision == "dismissed":
                    continue
                text = snapshots[Path(ticket.path)].decode("utf-8")
                approved = decision == "approved"
                receipt = T.plan_revision(ticket, contract) if approved else "pending"
                status = states["queue"][0] if approved else states["plan_changes"]
                text = T.field_text(T.status_text(text, status), "Plan-Approval", receipt)
                atomic_write_text((root / ticket.path).resolve(), text)
                if not approved and result.get("feedback"):
                    T.comment(root, ticket.path, f"Plannotator requested changes.\n\n{result['feedback']}")
        return {"decision": decision, "feedback": result.get("feedback"), "tickets": [t.ref for t in tickets]}

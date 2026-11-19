"""Independent acceptance checks; output is consumed by the learning gate."""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("calc", Path(sys.argv[1]) / "calc.py")
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
except Exception:
    print(json.dumps({"addition": False, "subtraction": False, "unsupported": False}))
    raise SystemExit


def check(a, op, b, expected):
    try:
        return module.calculate(a, op, b) == expected
    except Exception:
        return False


def unsupported():
    try:
        module.calculate(7, "*", 4)
    except ValueError:
        return True
    except Exception:
        return False
    return False


print(json.dumps({"addition": check(7, "+", 4, 11), "subtraction": check(7, "-", 4, 3),
                  "unsupported": unsupported()}))

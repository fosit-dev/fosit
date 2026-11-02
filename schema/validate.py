"""Validate FOSIT input files from the command line.

    python schema/validate.py kpi_history path/to/file.csv [--geo-unit cbsa|state|custom]

The rules themselves live in core/fosit (panel.py for KPI history), so the
browser (Pyodide) and this CLI run exactly the same checks. Validators for the
spend & delivery file and the locked plan arrive with the Read module.
Exit code: 0 = no errors (warnings allowed), 1 = errors found.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from fosit import api  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=["kpi_history"])
    parser.add_argument("path")
    parser.add_argument("--geo-unit", default="custom", choices=["cbsa", "state", "custom"])
    args = parser.parse_args()
    with open(args.path, encoding="utf-8-sig") as f:
        result = api.load_history(f.read(), args.geo_unit)
    for issue in result["issues"]:
        mark = "ERROR  " if issue["severity"] == "error" else "warning"
        print(f"{mark} {issue['code']}: {issue['message']}")
        if issue["examples"]:
            print(f"        e.g. {json.dumps(issue['examples'][:10])}")
    if result["ok"]:
        print("OK:", json.dumps(result["summary"]))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

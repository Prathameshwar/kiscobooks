"""Connect stock owners and enable native stock admission for Ubuntu installs.

Run after bootstrap has created the service environment files. Existing explicit
activation choices are retained so an operator can disable posting deliberately.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path


ROOT = Path("/opt/kiscobooks/current")
CONFIG = Path("/etc/kiscobooks")
SCRIPT = ROOT / "start/win/configure-stock-connections.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("stock_connections", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("stock connection configuration is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.configure(CONFIG, ROOT / "start/win/conf/services.json")
    for service, worker in (
        ("vouchers", "vouchers.tasks.source_worker"),
        ("vouchers", "vouchers.tasks.execution_worker"),
        ("accounting", "accounting.tasks.posting_delivery"),
    ):
        subprocess.run(
            [
                str(ROOT / "apis" / service / ".venv/bin/python"),
                "-m", worker, "--env-file", str(CONFIG / f"{service}.env"),
                "--check-config",
            ],
            cwd=ROOT,
            check=True,
        )
    for service, key in (
        ("accounting", "ACCOUNTING_VOUCHER_STOCK_ENABLED"),
        ("vouchers", "VOUCHERS_STOCK_EXECUTION_ENABLED"),
    ):
        environment = module.Environment(CONFIG, service)
        if key not in environment.values:
            environment.set(key, "true")
            environment.path.write_text("\n".join(environment.lines) + "\n", encoding="utf-8")
        os.chmod(environment.path, 0o640)
        subprocess.run(["chown", "root:kiscobooks", str(environment.path)], check=True)
    for service in ("identity", "catalog"):
        path = CONFIG / f"{service}.env"
        os.chmod(path, 0o640)
        subprocess.run(["chown", "root:kiscobooks", str(path)], check=True)
    print("Stock owner connections and installation defaults configured.")


if __name__ == "__main__":
    main()

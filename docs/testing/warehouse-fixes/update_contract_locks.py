"""Update only editable local contract versions when the uv launcher is unavailable."""

import re
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[3]
contracts = {
    name: tomllib.loads((root / "clients" / directory / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for name, directory in [("voucher-execution-client", "voucher-execution"), ("reporting-contract", "reporting")]
}
for path in [*root.glob("apis/*/uv.lock"), *root.glob("clients/*/uv.lock")]:
    content = path.read_text(encoding="utf-8")
    updated = content
    for name, version in contracts.items():
        pattern = r'(?m)(^name = "' + re.escape(name) + r'"\nversion = ")[^"]+("\nsource = \{ editable = [^\n]+\})'
        updated = re.sub(pattern, lambda match: match[1] + version + match[2], updated)
    if updated != content:
        tomllib.loads(updated)
        path.write_text(updated, encoding="utf-8")
        print(path.relative_to(root))

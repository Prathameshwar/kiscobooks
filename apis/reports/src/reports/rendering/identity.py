"""Content identity includes formatting, isolation, templates and pinned dependencies."""

import hashlib
import platform
from importlib.metadata import version
from pathlib import Path

from billing_platform import bulk_files, display, process_limits

from reports.domain.reporting import contracts


def implementation() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    paths = [*root.glob("*.py"), *root.joinpath("assets").glob("*")]
    for module in (bulk_files, display, process_limits, contracts):
        if module.__file__ is None:
            raise ValueError("report dependency source is unavailable")
        paths.append(Path(module.__file__))
    for path in sorted((path for path in paths if path.is_file()), key=lambda path: path.name):
        data = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(path.name.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    digest.update(platform.python_version().encode())
    for dependency in ("Jinja2", "reportlab", "uharfbuzz", "XlsxWriter", "billing-platform"):
        digest.update(f"{dependency}=={version(dependency)}".encode())
    return digest.hexdigest()

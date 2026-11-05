"""Packaged immutable query runtimes retained while completed reports reference them."""

import hashlib
import platform
from importlib.metadata import version
from importlib.resources import files


def calculation_dependencies() -> str:
    """Bind shared decimal, storage conversion and cursor behavior without copying rules."""
    digest = hashlib.sha256()
    root = files("billing_platform")
    for name in (
        "constants.py",
        "exact.py",
        "money.py",
        "listing.py",
        "idempotency.py",
        "db/types.py",
    ):
        source = root.joinpath(name).read_bytes().replace(b"\r\n", b"\n")
        digest.update(name.encode() + b"\0" + source + b"\0")
    digest.update(platform.python_version().encode())
    for dependency in ("SQLAlchemy", "pydantic", "asyncmy"):
        digest.update(f"{dependency}=={version(dependency)}".encode())
    return digest.hexdigest()

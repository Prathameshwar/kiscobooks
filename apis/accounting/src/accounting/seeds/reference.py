"""Materialize versioned ISO data after migrations, before starting Accounting."""

import asyncio
import os

from billing_platform.reference import register_language
from billing_platform.reference.seed import apply_reference_seed


def main() -> None:
    register_language()
    url = os.environ.get("ACCOUNTING_DATABASE_URL")
    if not url:
        raise RuntimeError("ACCOUNTING_DATABASE_URL is required")
    asyncio.run(apply_reference_seed(url, datasets=("currency", "country", "state", "language")))


if __name__ == "__main__":
    main()

"""Regenerate the backend contract, or check it without changing files."""

import argparse
import asyncio
import json
import secrets
from pathlib import Path

from pydantic import SecretStr

from reports.config import Settings
from reports.main import create_app


async def specification() -> str:
    # No database connection or real credential is needed to build OpenAPI.
    app = create_app(
        Settings(
            database_url="mysql+asyncmy://localhost/reports",
            actor_signing_secret=SecretStr(secrets.token_hex(32)),
            artifact_signing_secret=SecretStr(secrets.token_hex(32)),
        )
    )
    try:
        return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    finally:
        await app.state.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "openapi.json"
    expected = asyncio.run(specification())
    if args.check:
        return int(not output.exists() or output.read_text(encoding="utf-8") != expected)
    output.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

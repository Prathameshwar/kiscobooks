"""Export Audit OpenAPI without contacting a database."""

import argparse
import asyncio
import json
import secrets
from pathlib import Path

from pydantic import SecretStr

from audit.config import Settings
from audit.main import create_app


async def specification() -> str:
    app = create_app(
        Settings(
            database_url="mysql+asyncmy://localhost/audit",
            actor_signing_secret=SecretStr(secrets.token_hex(32)),
            cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        )
    )
    try:
        return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    finally:
        await app.state.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    expected = asyncio.run(specification())
    if args.check:
        return int(not target.exists() or target.read_text() != expected)
    target.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Seed GENERAL through the ordinary scoped API; no database or source bypass.

    python -m catalog.seeds.classification --base-url URL --company UUID

Supply a JSON object on stdin with `headers` (current gateway authorization or
signed actor context) and optional `custom_fields`. Credentials are never argv,
logged, persisted or manufactured by this command. Run once per new company;
reruns preserve existing definitions and do not overwrite custom values.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx


async def seed_general(
    client: httpx.AsyncClient,
    company: uuid.UUID,
    *,
    headers: Mapping[str, str],
    custom_fields: Mapping[str, Any] | None = None,
) -> uuid.UUID:
    path = f"/v1/companies/{company}/item-groups"

    async def existing() -> uuid.UUID | None:
        response = await client.get(path, params={"code": "GENERAL", "limit": 1}, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"General seed lookup failed with status {response.status_code}")
        rows = response.json()["items"]
        if not rows:
            return None
        row = rows[0]
        if (
            row.get("code") != "GENERAL"
            or row.get("allowed_kind") != "BOTH"
            or row.get("is_active") is not True
        ):
            raise RuntimeError("General seed cannot verify the existing protected definition")
        return uuid.UUID(row["id"])

    result = await existing()
    if result is not None:
        return result
    response = await client.post(
        path,
        headers={**headers, "Idempotency-Key": "catalog.seed.general.v1"},
        json={
            "code": "GENERAL",
            "name": "General",
            "allowed_kind": "BOTH",
            "valid_from": "1000-01-01",
            "parent_group_id": None,
            "custom_fields": dict(custom_fields or {}),
        },
    )
    if response.status_code == 201:
        return uuid.UUID(response.json()["id"])
    if response.status_code == 409:
        result = await existing()
        if result is not None:
            return result
    raise RuntimeError(f"General seed creation failed with status {response.status_code}")


def settings(base_url: str, raw: str) -> tuple[dict[str, str], dict[str, Any]]:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("seed base URL requires a plain HTTPS origin")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTP is supported only on loopback")
    if len(raw.encode()) > 65536:
        raise ValueError("seed authorization input exceeds its bound")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) - {"headers", "custom_fields"}:
        raise ValueError("seed input requires headers and optional custom_fields")
    auth = data.get("headers")
    custom = data.get("custom_fields", {})
    if not isinstance(auth, dict) or not auth or not isinstance(custom, dict) or len(custom) > 128:
        raise ValueError("invalid seed authorization or custom values")
    allowed = {"authorization", "x-actor-context", "x-actor-signature"}
    if any(
        not isinstance(key, str)
        or key.lower() not in allowed
        or not isinstance(value, str)
        or not value
        or any(ord(c) < 32 for c in value)
        for key, value in auth.items()
    ):
        raise ValueError("unsupported seed authorization header")
    return auth, custom


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--company", type=uuid.UUID, required=True)
    args = parser.parse_args()
    try:
        headers, custom = settings(args.base_url, sys.stdin.read(65537))

        async def run() -> uuid.UUID:
            async with httpx.AsyncClient(
                base_url=args.base_url, timeout=30, follow_redirects=False, trust_env=False
            ) as client:
                return await seed_general(
                    client, args.company, headers=headers, custom_fields=custom
                )

        sys.stdout.write(str(asyncio.run(run())) + "\n")
    except (ValueError, RuntimeError, httpx.HTTPError, KeyError, TypeError):
        sys.stderr.write(
            "Catalog General seed failed; verify authority, source readiness and input.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

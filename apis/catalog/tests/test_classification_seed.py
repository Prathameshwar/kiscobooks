from __future__ import annotations

import io
import json
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from billing_platform.ids import uuid7

from catalog.seeds import classification as seed


@pytest.mark.parametrize(
    "origin",
    [
        "ftp://example.com",
        "https://u:p@example.com",
        "https://example.com/path",
        "https://example.com?q=x",
        "https://example.com#x",
        "http://example.com",
        "https://",
    ],
)
def test_seed_rejects_unsafe_credential_targets(origin: str) -> None:
    with pytest.raises(ValueError):
        seed.settings(origin, '{"headers":{"Authorization":"Bearer token"}}')


@pytest.mark.parametrize(
    "raw",
    [
        "x" * 65537,
        "[]",
        '{"unknown":1}',
        "{}",
        '{"headers":{},"custom_fields":{}}',
        '{"headers":{"Authorization":"token"},"custom_fields":[]}',
        '{"headers":{"Cookie":"x"}}',
        '{"headers":{"Authorization":false}}',
        '{"headers":{"Authorization":""}}',
        '{"headers":{"Authorization":"a\\nb"}}',
    ],
    ids=[
        "oversize",
        "array",
        "unknown",
        "missing",
        "empty",
        "custom_type",
        "cookie",
        "nontext",
        "blank",
        "control",
    ],
)
def test_seed_rejects_unbounded_or_unsupported_authorization(raw: str) -> None:
    with pytest.raises(ValueError):
        seed.settings("https://catalog.example", raw)


def test_seed_input_preserves_authority_without_building_credentials() -> None:
    auth, custom = seed.settings(
        "http://127.0.0.1:8000",
        json.dumps(
            {
                "headers": {"Authorization": "Bearer temporary"},
                "custom_fields": {"cf_note": "hello"},
            }
        ),
    )
    assert auth == {"Authorization": "Bearer temporary"}
    assert custom == {"cf_note": "hello"}


@pytest.mark.parametrize(
    "mode", ["lookup_denied", "existing_hidden", "create_denied", "race", "conflict_missing"]
)
async def test_seed_handles_race_and_errors_without_echoing_responses(mode: str) -> None:
    company, identity = uuid7(), uuid7()
    lookups = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal lookups
        if request.method == "GET":
            lookups += 1
            if mode == "lookup_denied":
                return httpx.Response(403, json={"secret": "must not escape"})
            if mode == "existing_hidden":
                return httpx.Response(200, json={"items": [{"id": str(identity)}]})
            rows = (
                [
                    {
                        "id": str(identity),
                        "code": "GENERAL",
                        "is_active": True,
                        "allowed_kind": "BOTH",
                    }
                ]
                if mode == "race" and lookups > 1
                else []
            )
            return httpx.Response(200, json={"items": rows})
        return httpx.Response(
            422 if mode == "create_denied" else 409, json={"secret": "must not escape"}
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://catalog.example"
    ) as client:
        if mode == "race":
            assert (
                await seed.seed_general(client, company, headers={"Authorization": "temporary"})
                == identity
            )
        else:
            with pytest.raises(RuntimeError) as raised:
                await seed.seed_general(client, company, headers={"Authorization": "temporary"})
            assert "must not escape" not in str(raised.value)


def test_seed_cli_outputs_only_identity_or_safe_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    company, identity = uuid7(), uuid7()
    monkeypatch.setattr(
        sys, "argv", ["seed", "--base-url", "https://catalog.example", "--company", str(company)]
    )
    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"headers":{"Authorization":"Bearer private-token"}}')
    )

    original_client = httpx.AsyncClient

    @asynccontextmanager
    async def connection(**kwargs: Any) -> AsyncIterator[httpx.AsyncClient]:
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        async with original_client() as value:
            yield value

    async def create(connection: httpx.AsyncClient, target: uuid.UUID, **kwargs: Any) -> uuid.UUID:
        assert target == company and kwargs["headers"]["Authorization"] == "Bearer private-token"
        return identity

    monkeypatch.setattr(httpx, "AsyncClient", connection)
    monkeypatch.setattr(seed, "seed_general", create)
    assert seed.main() == 0
    assert capsys.readouterr().out.strip() == str(identity)
    monkeypatch.setattr(sys, "stdin", io.StringIO("private-token-invalid-json"))
    assert seed.main() == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "private-token" not in captured.err


def test_seed_module_entrypoint_exits_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr(
        sys, "argv", ["seed", "--base-url", "https://catalog.example", "--company", str(uuid7())]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO("invalid"))
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(seed.__file__), run_name="__main__")
    assert stopped.value.code == 1

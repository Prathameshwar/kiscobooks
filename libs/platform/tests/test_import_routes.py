"""Exercise the shared HTTP contract independently of owner business policies."""

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest_asyncio
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.errors import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    PlatformError,
)
from billing_platform.ids import uuid7
from billing_platform.import_routes import router_for
from billing_platform.rate_limit import WindowLimiter
from tests.test_import_framework import Adapter, file, row


@pytest_asyncio.fixture
async def boundary(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> AsyncIterator[tuple[httpx.AsyncClient, Adapter, str]]:
    adapter = Adapter(tenant_a)
    app = FastAPI()
    app.state.session_factory = factory
    app.state.settings = SimpleNamespace(
        actor_signing_secret=SecretStr("ephemeral-import-tests-signing-material")
    )
    app.state.write_limiter = WindowLimiter()

    async def actor(company_id: uuid.UUID, x_test_actor: str | None = Header(None)) -> Adapter:
        if x_test_actor is None:
            raise AuthenticationRequiredError("actor required")
        if company_id != adapter.company:
            raise PermissionDeniedError("wrong company")
        return adapter

    def build(request: Request, current: Adapter, company: uuid.UUID) -> Adapter:
        return current

    @app.exception_handler(PlatformError)
    async def failure(request: Request, exc: PlatformError) -> JSONResponse:
        return JSONResponse(exc.envelope().model_dump(mode="json"), status_code=exc.status_code)

    app.include_router(router_for("example", actor, build))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://imports.test",
        headers={"X-Test-Actor": "test", "Idempotency-Key": str(uuid7())},
    ) as client:
        yield client, adapter, f"/v1/companies/{adapter.company}"


async def post(
    client: httpx.AsyncClient, path: str, body: dict[str, Any], expected: int = 200
) -> dict[str, Any]:
    response = await client.post(path, json=body, headers={"Idempotency-Key": str(uuid7())})
    assert response.status_code == expected, response.text
    return dict(response.json())


async def test_full_http_lifecycle_and_private_downloads(
    boundary: tuple[httpx.AsyncClient, Adapter, str],
) -> None:
    client, _, root = boundary
    paths = (await client.get("/openapi.json")).json()["paths"]
    download_path = "/v1/companies/{company_id}/import-jobs/{job_id}/download"
    assert "text/csv" in paths[download_path]["post"]["responses"]["200"]["content"]
    assert (await client.get(root + "/import-definitions")).json()["formats"] == [
        "CSV",
        "TSV",
        "XLSX",
    ]
    template = await post(client, root + "/import-templates", {"definition": "things"}, 201)
    template_path = root + "/import-templates/" + template["id"]
    assert (await client.get(template_path)).status_code == 200
    for fmt in ("CSV", "TSV", "XLSX"):
        assert (
            await client.get(template_path, params={"resource": "thing", "format": fmt})
        ).status_code == 200
    job = await post(
        client,
        root + "/import-jobs",
        {"template_id": template["id"], "files": [file([row("one")]).model_dump()]},
        201,
    )
    path = root + "/import-jobs/" + job["id"]
    assert (await client.get(path)).json()["id"] == job["id"]
    assert (await client.get(root + "/import-jobs")).json()["page"]["limit"] == 50
    assert (await client.get(path + "/records")).json()["items"][0]["status"] is None
    reviewed = await post(client, path + "/validate", {"expected_version": 1})
    assert reviewed["state"] == "READY"
    for kind in ("attempts", "revisions", "artifacts"):
        assert (await client.get(path + "/history/" + kind)).status_code == 200
    attempt = (await client.get(path + "/history/attempts")).json()["items"][0]
    assert (await client.get(path + "/attempts/" + attempt["id"] + "/issues")).json()["items"] == []
    ticket = await post(client, path + "/download-ticket", {"kind": "NORMALIZED", "format": "TSV"})
    downloaded = await client.post(
        path + "/download", json={"kind": "NORMALIZED", "format": "TSV", "token": ticket["token"]}
    )
    assert downloaded.status_code == 200 and downloaded.headers["Cache-Control"] == "no-store"
    wrong = await client.post(path + "/download", json={"token": ticket["token"]})
    assert wrong.status_code == 409
    final = await post(
        client,
        path + "/commit",
        {"expected_version": reviewed["row_version"], "review_digest": reviewed["review_digest"]},
    )
    assert final["state"] == "SUCCEEDED"


async def test_correction_retry_and_cancel_are_exposed(
    boundary: tuple[httpx.AsyncClient, Adapter, str],
) -> None:
    client, adapter, root = boundary
    template = await post(client, root + "/import-templates", {"definition": "things"}, 201)
    job = await post(
        client,
        root + "/import-jobs",
        {"template_id": template["id"], "files": [file([row("one")]).model_dump()]},
        201,
    )
    path = root + "/import-jobs/" + job["id"]
    adapter.failing = {"one"}
    invalid = await post(client, path + "/validate", {"expected_version": 1})
    attempt = (await client.get(path + "/history/attempts")).json()["items"][0]
    assert (await client.get(path + "/attempts/" + attempt["id"] + "/issues")).json()["items"][0][
        "code"
    ] == "conflict"
    revised = await post(
        client,
        path + "/revisions",
        {"expected_version": invalid["row_version"], "files": [file([row("one")]).model_dump()]},
    )
    adapter.failing.clear()
    ready = await post(client, path + "/retry", {"expected_version": revised["row_version"]})
    assert ready["state"] == "READY"
    cancelled = await post(client, path + "/cancel", {"expected_version": ready["row_version"]})
    assert cancelled["state"] == "CANCELLED"


async def test_requests_fail_closed_at_the_boundary(
    boundary: tuple[httpx.AsyncClient, Adapter, str],
) -> None:
    client, adapter, root = boundary
    assert (await client.get(root + "/import-jobs?unknown=1")).status_code == 422
    assert (await client.get(root + "/import-jobs?limit=1&limit=2")).status_code == 422
    assert (await client.get(root + "/import-jobs?limit=201")).status_code == 422
    template = await post(client, root + "/import-templates", {"definition": "things"}, 201)
    assert (
        await client.get(root + "/import-templates/" + template["id"], params={"format": "CSV"})
    ).status_code == 422
    adapter.denied = True
    assert (await client.get(root + "/import-jobs")).status_code == 403
    adapter.denied = False
    async with httpx.AsyncClient(
        transport=client._transport, base_url="http://imports.test"
    ) as unauthenticated:
        assert (await unauthenticated.get(root + "/import-jobs")).status_code == 401
        assert (
            await unauthenticated.post(
                root + "/import-templates",
                json={"definition": "things"},
                headers={"X-Test-Actor": "test"},
            )
        ).status_code == 422

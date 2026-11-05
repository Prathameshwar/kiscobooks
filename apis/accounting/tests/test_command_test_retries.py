"""Native setup rehearsals follow the same explicit busy/replay contract as clients."""

import httpx
import pytest

from tests.test_masters import post


async def test_native_setup_retry_retains_exact_body_and_key():
    observed = []

    async def handler(request):
        observed.append((request.content, request.headers["idempotency-key"]))
        if len(observed) == 1:
            return httpx.Response(
                409,
                json={"error": {"message": "request is busy; retry with the same idempotency key"}},
            )
        return httpx.Response(201, json={"id": "retained-result"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://accounting.test"
    ) as client:
        assert await post(client, "/test", {"name": "same request"}) == {"id": "retained-result"}
    assert len(observed) == 2 and observed[0] == observed[1]


@pytest.mark.parametrize("status", [403, 409, 422, 500])
async def test_other_native_setup_failures_are_not_retried_or_hidden(status):
    observed = []

    async def handler(request):
        observed.append(request)
        return httpx.Response(status, json={"error": {"message": "A real failure"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://accounting.test"
    ) as client:
        with pytest.raises(AssertionError):
            await post(client, "/test", {})
    assert len(observed) == 1

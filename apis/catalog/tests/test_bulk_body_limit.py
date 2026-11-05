from collections.abc import AsyncIterator

import httpx


async def test_bulk_body_is_bounded_while_streaming_before_json_allocation(
    client: httpx.AsyncClient,
) -> None:
    consumed = 0

    async def chunks() -> AsyncIterator[bytes]:
        nonlocal consumed
        for _ in range(28):
            consumed += 1
            yield b"x" * (512 * 1024)

    response = await client.post(
        "/v1/companies/00000000-0000-0000-0000-000000000001/bulk-jobs",
        headers={"Content-Type": "application/json", "Idempotency-Key": "oversized"},
        content=chunks(),
    )
    assert response.status_code == 413, response.text
    assert consumed == 27
    assert set(response.json()) == {"error"}

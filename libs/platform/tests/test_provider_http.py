import httpx
import pytest

from billing_platform.provider_http import ProviderHttpError, provider_json


async def test_transport_preserves_closed_request_and_expected_json():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"link": "opaque-provider-value"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await provider_json(
            http,
            "POST",
            "https://provider.test/recovery/",
            headers={"Authorization": "Bearer private-test-value"},
            body={"token_duration": "minutes=10"},
            max_bytes=1024,
        )
    assert result == {"link": "opaque-provider-value"}
    assert len(requests) == 1 and requests[0].method == "POST"
    assert requests[0].headers["authorization"] == "Bearer private-test-value"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(307, headers={"location": "https://evil.test/"}),
        httpx.Response(403, text="private-provider-error"),
        httpx.Response(200, text="private-provider-error"),
        httpx.Response(200, json=["private-provider-error"]),
        httpx.Response(200, content=b"x" * 1025),
    ],
)
async def test_transport_bounds_responses_refuses_redirects_and_redacts_errors(response):
    requests = []

    def handler(request):
        requests.append(request)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ProviderHttpError) as error:
            await provider_json(
                http, "GET", "https://provider.test/user/", headers={}, max_bytes=1024
            )
        assert "private-provider-error" not in str(error.value)
    assert len(requests) == 1 and requests[0].url.host == "provider.test"


async def test_transport_accepts_native_email_ack_without_a_body():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(204))
    ) as http:
        assert (
            await provider_json(
                http,
                "POST",
                "https://provider.test/email/",
                headers={},
                max_bytes=1024,
                expected_status=204,
            )
            == {}
        )


async def test_transport_does_not_retry_a_timeout():
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("private-provider-value", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ProviderHttpError) as error:
            await provider_json(
                http, "POST", "https://provider.test/email/", headers={}, max_bytes=1024
            )
        assert "private-provider-value" not in str(error.value)
    assert len(requests) == 1

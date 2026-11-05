import secrets
import ssl
import uuid

import httpx
import pytest
from pydantic import SecretStr

from identity.config import Settings
from identity.services.account_provider import AccountProvider, AccountProviderUnavailableError
from identity.services.provider_transport import provider_client


async def test_api_and_worker_transport_keep_tls_verification_and_fail_on_invalid_ca(tmp_path):
    configured = settings()
    async with provider_client(configured) as client:
        assert client.follow_redirects is False
    ca = tmp_path / "invalid-ca.pem"
    ca.write_text("not a certificate")
    configured.authentik_ca_file = str(ca)
    with pytest.raises(ssl.SSLError):
        provider_client(configured)


def settings():
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr(secrets.token_hex(32)),
        cursor_signing_secret=SecretStr(secrets.token_hex(32)),
        authentik_review_url="https://provider.test",
        authentik_review_token=SecretStr(secrets.token_hex(32)),
    )


def record(**changes):
    return {
        "pk": 42,
        "uuid": str(uuid.uuid4()),
        "uid": secrets.token_hex(32),
        "name": "Applicant",
        "username": "applicant",
        "email": "applicant@example.invalid",
        "path": "bill/pending-registration",
        "type": "external",
        "is_active": False,
        "groups": [],
        "roles": [],
        "attributes": {
            "billing_email_verified": False,
            "billing_registration_region": {"country_code": "IN", "state_code": "IN-MH"},
            "unrelated": "retained",
        },
        **changes,
    }


def test_uses_immutable_uuid_and_rejects_unrelated_provider_accounts():
    value = record()
    row = AccountProvider.applicant(value)
    assert str(row.provider_uuid) == value["uuid"]
    with pytest.raises(AccountProviderUnavailableError):
        AccountProvider.applicant(record(type="internal"))


def test_imports_workspace_request_and_distinguishes_invitation_from_legacy():
    new = record()
    new["attributes"]["billing_registration_workspace_name"] = "North Books"
    assert AccountProvider.applicant(new).workspace_name == "North Books"
    invited = record()
    invited["attributes"]["billing_registration_workspace_name"] = ""
    assert AccountProvider.applicant(invited).workspace_name == ""
    assert AccountProvider.applicant(record()).workspace_name is None


def test_hashed_oidc_subject_is_provider_uid_and_invalid_uid_is_rejected():
    value = record()
    assert AccountProvider.subject(value) == value["uid"]
    assert AccountProvider.subject(value) != value["uuid"]
    with pytest.raises(AccountProviderUnavailableError):
        AccountProvider.subject(record(uid="invalid"))


async def test_fixed_adapter_preserves_attributes_and_updates_no_credentials():
    requests = []
    value = record()

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=value)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        provider = AccountProvider(settings(), http)
        await provider.read(42)
        await provider.apply(42, value, active=True, verified=True, command_id=uuid.uuid4())
    import json

    body = json.loads(requests[-1].content)
    assert set(body) == {"is_active", "attributes"}
    assert body["attributes"]["unrelated"] == "retained"
    assert body["attributes"]["billing_registration_region"] == {
        "country_code": "IN",
        "state_code": "IN-MH",
    }
    assert all(request.url.host == "provider.test" for request in requests)


async def test_provider_failure_is_safe_and_does_not_return_raw_response():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, text="sensitive provider error")
        )
    ) as http:
        with pytest.raises(AccountProviderUnavailableError) as error:
            await AccountProvider(settings(), http).read(42)
    assert "sensitive" not in str(error.value)


async def test_exact_pending_email_lookup_checks_provider_results():
    wanted = record(email="Owner@Example.invalid")
    unrelated = record(email="another@example.invalid")
    active = record(email="owner@example.invalid", is_active=True)

    def respond(request):
        assert request.url.params["email"] == "owner@example.invalid"
        assert request.url.params["path"] == "bill/pending-registration"
        return httpx.Response(
            200,
            json={"results": [wanted, unrelated, active], "pagination": {"next": 0}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        rows = await AccountProvider(settings(), http).pending_email("owner@example.invalid")
    assert len(rows) == 1 and rows[0].email == wanted["email"]


@pytest.mark.parametrize(
    "changes",
    [
        {"is_active": "false"},
        {"attributes": []},
        {"name": 4},
        {"groups": [1]},
        {"is_superuser": True},
    ],
)
def test_malformed_or_privileged_profile_is_denied(changes):
    with pytest.raises(AccountProviderUnavailableError):
        AccountProvider.applicant(record(**changes))


async def test_oversized_provider_body_is_rejected_before_parsing():
    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(3):
                yield b"x" * 1_000_000

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Oversized()))
    ) as http:
        with pytest.raises(AccountProviderUnavailableError):
            await AccountProvider(settings(), http).read(42)


@pytest.mark.parametrize("next_page,has_more", [(0, False), (2, True)])
async def test_native_integer_pagination(next_page, has_more):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"results": [record()], "pagination": {"next": next_page}}
            )
        )
    ) as http:
        rows, more = await AccountProvider(settings(), http).page()
        assert len(rows) == 1 and more is has_more


@pytest.mark.parametrize("next_page", [-1, 10001, "2", None, True])
async def test_malformed_provider_pagination_is_denied(next_page):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"results": [], "pagination": {"next": next_page}})
        )
    ) as http:
        with pytest.raises(AccountProviderUnavailableError):
            await AccountProvider(settings(), http).page()

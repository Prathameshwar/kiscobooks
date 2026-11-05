import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from notification.providers import MetaWhatsAppAdapter, SendCommand, TwilioSmsAdapter
from notification.providers.normalize import extract_callback_facts, valid_attempt_key

KEY = "019a0000-0000-7000-8000-000000000001:1"


async def test_ses_correlation_tags_obey_vendor_character_rules():
    from notification.providers import SesAdapter

    class Client:
        async def send_email(self, **kwargs):
            tag = kwargs["EmailTags"][0]
            assert tag["Name"] == "attempt_key" and tag["Value"] == KEY.replace(":", "_")
            return {"MessageId": "ses-message"}

    assert (
        await SesAdapter(Client()).send(SendCommand("destination", "sender", "body", None, KEY))
    ).outcome == "accepted"


async def test_twilio_callback_url_binds_the_attempt_in_the_signed_url():
    async def handler(request):
        params = parse_qs(request.content.decode())
        callback = urlsplit(params["StatusCallback"][0])
        assert parse_qs(callback.query)["attempt_key"] == [KEY]
        return httpx.Response(201, json={"sid": "native-sms"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TwilioSmsAdapter(
            client,
            account_sid="test",
            auth_token="test",
            callback_url="https://callback.invalid/v1/callbacks/sms/key",
        )
        assert (
            await provider.send(SendCommand("destination", "sender", "body", None, KEY))
        ).outcome == "accepted"


async def test_meta_outgoing_reference_is_echoed_by_signed_status_facts():
    async def handler(request):
        assert json.loads(request.content)["biz_opaque_callback_data"] == KEY
        return httpx.Response(200, json={"messages": [{"id": "native-wa"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MetaWhatsAppAdapter(client, access_token="test")
        await provider.send(
            SendCommand(
                "destination",
                "sender",
                "body",
                None,
                KEY,
                provider_template_name="name",
                template_language="en",
            )
        )
    body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "native-wa",
                                        "status": "delivered",
                                        "biz_opaque_callback_data": KEY,
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    assert extract_callback_facts("whatsapp", body)[0].attempt_key == KEY


@pytest.mark.parametrize(
    "value", [None, "unexpected", "019a0000-0000-7000-8000-000000000001:0", "x" * 100]
)
def test_untrusted_attempt_reference_shapes_are_not_used(value):
    assert valid_attempt_key(value) is None

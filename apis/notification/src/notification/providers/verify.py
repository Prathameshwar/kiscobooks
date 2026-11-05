"""Per-channel provider callback signature verification (docs/notification.md §2.2).

Each provider signs its callbacks differently; a single generic HMAC is wrong for at least
one of them. This dispatches by channel:

* **Meta (WhatsApp)** and the generic default — ``X-Hub-Signature-256`` style: HMAC-SHA256
  over the raw body, hex, optionally ``sha256=``-prefixed. (``billing_platform.webhooks``.)
* **Twilio (SMS)** — ``X-Twilio-Signature``: base64(HMAC-**SHA1**(auth_token, url + the
  request's POST params concatenated in sorted key order)). SHA-1 is the provider's scheme,
  not our choice.
* **SES via SNS (email)** — the public callback exclusively uses the RSA verifier in
  ``providers.sns``; there is no shared-secret fallback for email.

Behind nginx the public URL Twilio signed is reconstructed from deployment configuration;
the caller passes that trusted ``url``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from billing_platform.errors import PermissionDeniedError
from billing_platform.webhooks import verify_sha256_hmac


def verify_twilio(
    *, url: str, params: dict[str, str] | dict[str, list[str]], secret: bytes, signature: str
) -> None:
    """Twilio's ``X-Twilio-Signature`` scheme. Raises 403 on mismatch."""
    data = url
    for key in sorted(params):
        value = params[key]
        for item in sorted(set(value if isinstance(value, list) else [value])):
            data += key + item
    digest = hmac.new(secret, data.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    if not hmac.compare_digest(expected, signature):
        raise PermissionDeniedError("invalid callback signature")


def verify_callback(
    channel: str,
    *,
    body: bytes,
    secret: bytes,
    signature: str,
    url: str,
    form_params: dict[str, str] | dict[str, list[str]],
) -> None:
    """Verify a provider callback for ``channel``, choosing the provider's scheme."""
    if channel == "sms":
        verify_twilio(url=url, params=form_params, secret=secret, signature=signature)
    else:
        # email (SES-SNS shared-secret / generic), whatsapp (Meta), push (FCM).
        verify_sha256_hmac(body, secret=secret, signature=signature)

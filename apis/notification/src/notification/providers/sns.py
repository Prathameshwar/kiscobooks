"""Native SNS signature verification; certificate URLs cannot become arbitrary fetches."""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from billing_platform.errors import PermissionDeniedError
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


async def certificate(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            result = bytearray()
            async for chunk in response.aiter_bytes():
                result.extend(chunk)
                if len(result) > 65536:
                    raise ValueError("SNS certificate exceeds limit")
            return bytes(result)


def canonical(message: dict[str, Any]) -> bytes:
    kind = message.get("Type")
    fields = (
        ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
        if kind == "Notification"
        else ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
    )
    if kind not in {"Notification", "SubscriptionConfirmation", "UnsubscribeConfirmation"}:
        raise ValueError("unsupported SNS envelope")
    return "".join(
        f"{key}\n{message[key]}\n" for key in fields if key != "Subject" or key in message
    ).encode()


async def verify_sns(
    body: bytes,
    *,
    allowed_topics: list[str],
    load_certificate: Callable[[str], Awaitable[bytes]] = certificate,
) -> dict[str, Any]:
    try:
        message = json.loads(body)
        if not isinstance(message, dict) or message.get("TopicArn") not in allowed_topics:
            raise ValueError("unexpected topic")
        required = [
            "Message",
            "MessageId",
            "Type",
            "TopicArn",
            "Timestamp",
            "Signature",
            "SignatureVersion",
            "SigningCertURL",
        ]
        if message.get("Type") != "Notification":
            required += ["SubscribeURL", "Token"]
        if any(not isinstance(message.get(field), str) for field in required):
            raise ValueError("invalid SNS field type")
        if not 1 <= len(message["MessageId"]) <= 255:
            raise ValueError("invalid SNS message identity")
        arn = message["TopicArn"].split(":")
        if len(arn) != 6 or arn[:3] not in [["arn", "aws", "sns"], ["arn", "aws-cn", "sns"]]:
            raise ValueError("invalid topic")
        region, suffix = arn[3], "amazonaws.com.cn" if arn[1] == "aws-cn" else "amazonaws.com"
        host = f"sns.{region}.{suffix}"
        url = urlsplit(message["SigningCertURL"])
        if (
            url.scheme != "https"
            or url.netloc != host
            or url.query
            or url.fragment
            or not re.fullmatch(r"/SimpleNotificationService-[a-zA-Z0-9_-]+\.pem", url.path)
        ):
            raise ValueError("untrusted signing certificate URL")
        timestamp = dt.datetime.fromisoformat(message["Timestamp"].replace("Z", "+00:00"))
        # SNS retries may legitimately arrive days later. Dedupe the signed MessageId;
        # reject future timestamps, rather than inventing a short retry-breaking TTL.
        if timestamp.tzinfo is None or timestamp > dt.datetime.now(dt.UTC) + dt.timedelta(
            minutes=5
        ):
            raise ValueError("invalid timestamp")
        pem = await load_certificate(url.geturl())
        cert = x509.load_pem_x509_certificate(pem)
        now = dt.datetime.now(dt.UTC)
        if not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc:
            raise ValueError("expired signing certificate")
        key = cert.public_key()
        if not isinstance(key, rsa.RSAPublicKey):
            raise ValueError("unsupported signing key")
        version = message.get("SignatureVersion")
        if version not in {"1", "2"}:
            raise ValueError("unsupported signature version")
        key.verify(
            base64.b64decode(message["Signature"], validate=True),
            canonical(message),
            padding.PKCS1v15(),
            hashes.SHA256() if version == "2" else hashes.SHA1(),  # noqa: S303 - SNS v1 signature protocol
        )
        if message["Type"] != "Notification":
            confirm = urlsplit(message["SubscribeURL"])
            query = parse_qs(confirm.query)
            if (
                confirm.scheme != "https"
                or confirm.netloc != host
                or confirm.fragment
                or query.get("TopicArn") != [message["TopicArn"]]
                or query.get("Action") != ["ConfirmSubscription"]
                or query.get("Token") != [message["Token"]]
            ):
                raise ValueError("untrusted confirmation URL")
        return message
    except (KeyError, TypeError, ValueError, RecursionError, InvalidSignature) as exc:
        raise PermissionDeniedError("invalid SNS callback") from exc

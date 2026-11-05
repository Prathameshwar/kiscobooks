"""Ephemeral RSA material for native SNS fixtures; no credential is persisted."""

import base64
import datetime as dt
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from notification.providers.sns import canonical

TOPIC = "arn:aws:sns:us-east-1:123456789012:notification-test"
CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
now = dt.datetime.now(dt.UTC)
CERT = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(KEY.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(days=1))
    .not_valid_after(now + dt.timedelta(days=1))
    .sign(KEY, hashes.SHA256())
    .public_bytes(serialization.Encoding.PEM)
)


def envelope(payload: bytes) -> bytes:
    message = {
        "Type": "Notification",
        "Message": payload.decode(),
        "MessageId": __import__("hashlib").sha256(payload).hexdigest(),
        "TopicArn": TOPIC,
        "Timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "SigningCertURL": CERT_URL,
        "SignatureVersion": "2",
    }
    message["Signature"] = base64.b64encode(
        KEY.sign(canonical(message), padding.PKCS1v15(), hashes.SHA256())
    ).decode()
    return json.dumps(message).encode()


async def certificate(url: str) -> bytes:
    assert url == CERT_URL
    return CERT

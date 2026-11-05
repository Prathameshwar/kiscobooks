"""The production gateway template must carry what the local sign-in provider needs.

With ``AUTH_PROVIDER=local`` (the default) public sign-in is ``/oidc/*`` on Identity, and Identity
throttles on the client address uvicorn derives from ``X-Forwarded-For``. A template that does not
route ``/oidc/``, or passes the client's own header through, is a deployment where sign-in does not
work or where anyone chooses the address their limits are counted against.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = (ROOT / "deploy" / "nginx" / "identity.conf.example").read_text(encoding="utf-8")


def block(name: str) -> str:
    match = re.search(rf"location {re.escape(name)} \{{(?P<body>.*?)\n    \}}", TEMPLATE, re.S)
    assert match is not None, f"{name} is not in the template"
    return match.group("body")


def test_the_oidc_endpoints_are_routed_and_limited() -> None:
    oidc = block("/oidc/")
    assert "proxy_pass http://identity;" in oidc
    assert "limit_req zone=identity_auth" in oidc
    assert 'proxy_set_header X-Actor-Context "";' in oidc
    # The token and revoke bodies are small forms; nothing here needs the 1 MB site default.
    assert re.search(r"client_max_body_size 16k;", oidc)


def test_the_bff_surface_is_not_public() -> None:
    assert "location /internal/ { return 404; }" in TEMPLATE


@pytest.mark.parametrize("name", ["/oidc/", "/v1/", "= /_identity_auth"])
def test_every_path_to_identity_overwrites_the_forwarded_address(name: str) -> None:
    """Passing the client's X-Forwarded-For through lets it pick the address that is throttled."""
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in block(name)


def test_nothing_forwards_the_clients_own_header_unchanged() -> None:
    assert "$http_x_forwarded_for" not in TEMPLATE

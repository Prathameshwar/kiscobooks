"""Verified provider TLS shared by request and background approval paths."""

import ssl

import httpx

from identity.config import Settings


def provider_client(settings: Settings) -> httpx.AsyncClient:
    trust = ssl.create_default_context()
    if settings.authentik_ca_file:
        trust.load_verify_locations(cafile=settings.authentik_ca_file)
    return httpx.AsyncClient(timeout=5, follow_redirects=False, verify=trust)

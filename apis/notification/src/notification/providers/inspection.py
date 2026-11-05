"""Provider-authoritative setup checks. Called only outside SQL transactions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from notification.domain.provider_template import matches as template_matches
from notification.models import (
    ProviderAccount,
    ProviderTemplateBinding,
    SenderIdentity,
    TemplateVersion,
)
from notification.providers.aws import client as aws_client


@dataclass(frozen=True)
class Inspection:
    success: bool
    reason: str
    verification_status: str | None = None
    approval_status: str | None = None


async def inspect_provider(
    provider: ProviderAccount,
    credentials: dict[str, Any],
    kind: str,
    *,
    sender: SenderIdentity | None = None,
    binding: ProviderTemplateBinding | None = None,
    version: TemplateVersion | None = None,
    client: httpx.AsyncClient,
) -> Inspection:
    if provider.provider_key == "ses":
        if not provider.region:
            return Inspection(False, "provider_region_required")
        ses = await asyncio.to_thread(aws_client, "sesv2", provider.region, credentials)
        if sender is not None:
            if kind == "sender.verify":
                await asyncio.to_thread(
                    ses.create_email_identity, EmailIdentity=sender.external_sender_id
                )
            data = await asyncio.to_thread(
                ses.get_email_identity, EmailIdentity=sender.external_sender_id
            )
            verified = bool(data.get("VerifiedForSendingStatus"))
            return Inspection(
                True,
                "verified" if verified else "verification_pending",
                verification_status="verified" if verified else "unverified",
            )
        data = await asyncio.to_thread(ses.get_account)
        return Inspection(bool(data.get("SendingEnabled")), "account_checked")
    if provider.provider_key == "twilio":
        account = credentials["account_sid"]
        auth = httpx.BasicAuth(account, credentials["auth_token"])
        root = f"https://api.twilio.com/2010-04-01/Accounts/{account}"
        if sender:
            response = await client.get(
                root + "/IncomingPhoneNumbers.json",
                auth=auth,
                params={"PhoneNumber": sender.external_sender_id, "PageSize": 1},
            )
            response.raise_for_status()
            numbers = response.json().get("incoming_phone_numbers", [])
            verified = any(
                r.get("phone_number") == sender.external_sender_id
                and r.get("capabilities", {}).get("sms")
                for r in numbers
            )
            return Inspection(
                True, "sender_checked", verification_status="verified" if verified else "unverified"
            )
        response = await client.get(root + ".json", auth=auth)
        response.raise_for_status()
        return Inspection(response.json().get("status") == "active", "account_checked")
    if provider.provider_key == "meta":
        api_version = credentials.get("api_version", "v23.0")
        headers = {"Authorization": f"Bearer {credentials['access_token']}"}
        root = f"https://graph.facebook.com/{api_version}"
        if binding:
            business = credentials["business_account_id"]
            response = await client.get(
                f"{root}/{business}/message_templates",
                headers=headers,
                params={
                    "name": binding.external_name,
                    "fields": "id,name,language,status,components",
                    "limit": 100,
                },
            )
            response.raise_for_status()
            match = next(
                (
                    r
                    for r in response.json().get("data", [])
                    if r.get("id") == binding.external_template_id
                    and r.get("name") == binding.external_name
                    and r.get("language") == binding.external_language
                ),
                None,
            )
            if match is None:
                return Inspection(True, "provider_template_not_found", approval_status="rejected")
            status = str(match.get("status", "PENDING")).lower()
            if status == "approved" and (
                version is None
                or not template_matches(
                    version.body_text, version.channel_payload, match.get("components")
                )
            ):
                return Inspection(
                    True, "provider_template_content_mismatch", approval_status="rejected"
                )
            return Inspection(
                True,
                "provider_template_checked",
                approval_status=status if status in {"approved", "rejected"} else "pending",
            )
        phone = sender.external_sender_id if sender else credentials["phone_number_id"]
        response = await client.get(
            f"{root}/{phone}",
            headers=headers,
            params={"fields": "id,code_verification_status,display_phone_number"},
        )
        response.raise_for_status()
        verified = response.json().get("code_verification_status") == "VERIFIED"
        return Inspection(
            True, "sender_checked", verification_status="verified" if verified else "unverified"
        )
    return Inspection(False, "provider_inspection_not_supported")

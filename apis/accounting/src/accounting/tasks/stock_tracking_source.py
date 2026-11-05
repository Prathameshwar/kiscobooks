"""Read published Catalog facts as the original caller, before the Accounting transaction."""

import datetime as dt
import hashlib
import json
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from billing_platform.errors import PermissionDeniedError, PlatformError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from pydantic import ValidationError

from accounting.api.auth import Access
from accounting.config import Settings
from accounting.schemas.stock_tracking import TrackingSource


class TrackingSourceUnavailableError(PlatformError):
    status_code = 503
    code = "source_unavailable"


async def tracking_source(
    settings: Settings,
    access: Access,
    item: uuid.UUID,
    date: dt.date,
    authorization: str | None,
    step_up: str | None = None,
    *,
    include_identifiers: bool = True,
) -> TrackingSource:
    origin = settings.stock_catalog_url
    if not origin or not authorization or not authorization.startswith("Bearer "):
        raise TrackingSourceUnavailableError("Catalog tracking verification is not configured")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise TrackingSourceUnavailableError("Catalog tracking verification is not configured")
    company = access.context.company_id
    base = origin.rstrip("/") + f"/v1/companies/{company}"
    headers = {
        "Authorization": authorization,
        **({"X-Company-Step-Up": step_up} if step_up else {}),
    }
    async with httpx.AsyncClient(
        timeout=8, follow_redirects=False, headers=headers, trust_env=False
    ) as client:

        async def get(path: str) -> dict[str, Any]:
            try:
                async with client.stream("GET", base + path) as response:
                    if response.status_code == 403:
                        raise PermissionDeniedError(
                            "Catalog read authority is required to verify tracking"
                        )
                    if response.status_code != 200:
                        raise TrackingSourceUnavailableError(
                            "published product tracking facts are unavailable"
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        content.extend(chunk)
                        if len(content) > 262144:
                            raise TrackingSourceUnavailableError(
                                "product tracking source exceeds its response bound"
                            )
                data: Any = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("invalid source shape")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                raise TrackingSourceUnavailableError(
                    "published product tracking facts are unavailable"
                ) from exc

        item_data = await get(f"/items/{item}")
        if (
            item_data.get("id") != str(item)
            or item_data.get("company_id") != str(company)
            or item_data.get("status") != "ACTIVE"
        ):
            raise ValidationFailedError("an active goods SKU with verified tracking is required")
        try:
            family_id = uuid.UUID(item_data["family_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TrackingSourceUnavailableError(
                "readable SKU family ownership is required"
            ) from exc
        family = await get(f"/product-families/{family_id}")
        if (
            family.get("id"),
            family.get("company_id"),
            family.get("status"),
            family.get("kind"),
        ) != (str(family_id), str(company), "ACTIVE", "GOODS"):
            raise TrackingSourceUnavailableError("an active goods family is required")
        # Future product defaults do not replace an active SKU's instantiated profile.
        selected = await get(f"/item-inventory-profiles?item_id={item}&limit=2")
        candidates = selected.get("items")
        if (
            not isinstance(candidates, list)
            or len(candidates) != 1
            or candidates[0].get("item_id") != str(item)
            or selected.get("page", {}).get("has_more") is not False
        ):
            raise TrackingSourceUnavailableError("an activated SKU inventory profile is required")
        try:
            activated_id = uuid.UUID(candidates[0]["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TrackingSourceUnavailableError("SKU inventory profile is unavailable") from exc
        activated = await get(f"/item-inventory-profiles/{activated_id}")
        if (
            activated.get("id") != str(activated_id)
            or activated.get("company_id") != str(company)
            or activated.get("item_id") != str(item)
            or activated.get("base_unit_id") != item_data.get("base_unit_id")
        ):
            raise TrackingSourceUnavailableError("SKU inventory profile ownership is unavailable")
        try:
            profile_id = uuid.UUID(activated["template_revision_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TrackingSourceUnavailableError(
                "a readable published inventory profile is required"
            ) from exc
        choices = await get(
            f"/product-configuration/options/inventory-template-revisions?value={profile_id}"
        )
        owners = [
            value.get("parent_id")
            for value in choices.get("items", [])
            if value.get("value") == str(profile_id)
        ]
        try:
            if len(owners) != 1:
                raise ValueError("ambiguous revision owner")
            owner_id = uuid.UUID(owners[0])
        except (TypeError, ValueError) as exc:
            raise TrackingSourceUnavailableError(
                "published inventory profile ownership is unavailable"
            ) from exc
        profile = await get(f"/inventory-templates/{owner_id}/revisions/{profile_id}")
        if (
            profile.get("id") != str(profile_id)
            or profile.get("company_id") != str(company)
            or profile.get("template_id") != str(owner_id)
            or not profile.get("published_at")
        ):
            raise TrackingSourceUnavailableError(
                "inventory profile publication could not be verified"
            )
        requirements = []
        normalization = 1
        source_keys = {
            "lot_tracking",
            "serial_tracking",
            "expiry_required",
            "manufacture_date_required",
            "shelf_life_days",
            "minimum_remaining_life_days",
        }
        if (
            not source_keys <= profile.keys()
            or not source_keys <= activated.keys()
            or any(profile[key] != activated[key] for key in source_keys)
        ):
            raise TrackingSourceUnavailableError(
                "activated tracking requirements are protected or inconsistent"
            )
        if include_identifiers and profile.get("serial_tracking") is True:
            if activated.get("identifier_profile_id") != profile.get("identifier_profile_id"):
                raise TrackingSourceUnavailableError(
                    "activated identifier requirements are unavailable"
                )
            try:
                identifier_id = uuid.UUID(profile["identifier_profile_id"])
                unit_id = uuid.UUID(item_data["base_unit_id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise TrackingSourceUnavailableError(
                    "readable identifier and base-unit definitions are required"
                ) from exc
            identifiers = await get(f"/identifier-profiles/{identifier_id}")
            rules = await get(f"/identifier-profiles/{identifier_id}/requirements?limit=50")
            unit = await get(f"/units/{unit_id}")
            if (
                identifiers.get("id") != str(identifier_id)
                or identifiers.get("company_id") != str(company)
                or identifiers.get("is_active") is not True
                or identifiers.get("normalization_version") != 1
                or unit.get("id") != str(unit_id)
                or unit.get("company_id") != str(company)
                or unit.get("dimension") != "COUNT"
                or unit.get("decimal_places") != 0
                or unit.get("quantity_increment") not in {"1", "1.0000"}
                or unit.get("is_active") is not True
                or not isinstance(rules.get("items"), list)
                or not 1 <= len(rules["items"]) <= 2
                or rules.get("page", {}).get("has_more") is not False
            ):
                raise TrackingSourceUnavailableError(
                    "published serial requirements could not be verified"
                )
            for rule in rules["items"]:
                if rule.get("profile_id") != str(identifier_id):
                    raise TrackingSourceUnavailableError(
                        "identifier requirement ownership is unavailable"
                    )
                requirements.append(
                    {
                        key: rule.get(key)
                        for key in (
                            "identifier_type",
                            "namespace_rule",
                            "min_count",
                            "max_count",
                            "requires_slot",
                        )
                    }
                )
        values = {
            # Catalog's activated profile includes its validated per-product batch choice.
            key: activated.get(key)
            for key in (
                "lot_tracking",
                "serial_tracking",
                "expiry_required",
                "manufacture_date_required",
                "shelf_life_days",
                "minimum_remaining_life_days",
            )
        }
        try:
            return TrackingSource.model_validate(
                {
                    **values,
                    "company_id": company,
                    "item_id": item,
                    "as_of": date,
                    "profile_revision_id": profile_id,
                    "base_unit_id": item_data["base_unit_id"],
                    "requirements": requirements,
                    "normalization_version": normalization,
                    "source_digest": hashlib.sha256(
                        canonical_json(
                            {
                                "item": item_data,
                                "family": family,
                                "activated": activated,
                                "profile": profile,
                                "requirements": requirements,
                            }
                        )
                    ).hexdigest(),
                }
            )
        except ValidationError as exc:
            raise TrackingSourceUnavailableError(
                "tracking fields are protected or incomplete"
            ) from exc

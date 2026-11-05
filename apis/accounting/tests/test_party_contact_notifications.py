"""Party contacts publish purpose-specific snapshots atomically."""

import httpx
import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from sqlalchemy import select

from accounting.tasks.party_contact_notifications import _phone, backfill_company
from tests.conftest import COMPANY, TENANT
from tests.test_masters import activate, new_party, party, post, prepare


@pytest.mark.asyncio
async def test_accounting_contact_snapshot_tracks_active_use(
    client: httpx.AsyncClient, app,
) -> None:
    await prepare(client)
    owner = await party(client)
    contact = await post(client, "/party-contacts", {
        "party_id": owner["id"], "name": "Buyer accounts",
        "email": "BUYER@EXAMPLE.TEST", "mobile": "9876543210",
    })
    contact = await activate(client, "/party-contacts", contact)
    use = await post(client, "/party-contact-uses", {
        "party_id": owner["id"], "contact_id": contact["id"],
        "purpose": "INVOICING", "is_default": True,
    })
    await activate(client, "/party-contact-uses", use)
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            rows = list((await db.scalars(select(Outbox).where(
                Outbox.event_type == "accounting.party_contact.snapshot",
            ).order_by(Outbox.occurred_at, Outbox.id))).all())
            assert rows
            current = rows[-1].payload
            assert current["party_id"] == owner["id"]
            assert {
                (item["purpose"], item["channel"], item["destination"])
                for item in current["destinations"]
            } >= {
                ("INVOICING", "email", "buyer@example.test"),
                ("INVOICING", "sms", "+919876543210"),
            }
            assert current["source_version"] > rows[0].payload["source_version"]


def test_phone_normalizes_indian_mobile_and_rejects_invalid() -> None:
    assert _phone("98765 43210") == "+919876543210"
    assert _phone("+91-98765-43210") == "+919876543210"
    assert _phone("123") is None



def test_phone_projection_rejects_non_ascii_numerals() -> None:
    from accounting.tasks.party_contact_notifications import _phone

    assert _phone("\u0967\u0968\u0969\u096a\u096b\u096c\u096d\u096e\u096f\u0966") is None
    assert _phone("9876543210") == "+919876543210"



@pytest.mark.asyncio
async def test_backfill_emits_new_version_for_existing_party(
    client: httpx.AsyncClient, app,
) -> None:
    await prepare(client)
    owner = await party(client)
    contact = await post(client, "/party-contacts", {
        "party_id": owner["id"], "name": "Buyer",
        "email": "buyer@example.test",
    })
    contact = await activate(client, "/party-contacts", contact)
    await post(client, "/party-contact-uses", {
        "party_id": owner["id"], "contact_id": contact["id"],
        "purpose": "INVOICING", "is_default": True,
    })
    second = await new_party(client, code="DEF")
    second_contact = await post(client, "/party-contacts", {
        "party_id": second["id"], "name": "Other",
        "email": "other@example.test",
    })
    await post(client, "/party-contact-uses", {
        "party_id": second["id"], "contact_id": second_contact["id"],
        "purpose": "INVOICING", "is_default": True,
    })
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db, db.begin():
            count, last_id = await backfill_company(
                db, tenant_id=TENANT, company_id=COMPANY, limit=1,
            )
            assert count == 1 and last_id is not None
        async with app.state.session_factory() as db, db.begin():
            second_count, second_last = await backfill_company(
                db, tenant_id=TENANT, company_id=COMPANY,
                after_party_id=last_id, limit=1,
            )
            assert second_count == 1 and second_last != last_id
        async with app.state.session_factory() as db:
            rows = list((await db.scalars(select(Outbox).where(
                Outbox.event_type == "accounting.party_contact.snapshot",
            ).order_by(Outbox.occurred_at, Outbox.id))).all())
            assert rows[-1].payload["source_version"] > rows[0].payload["source_version"]

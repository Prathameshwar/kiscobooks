"""Real MySQL locking and atomic review/audit persistence on disposable rows."""

import asyncio
import secrets

import pytest
from billing_platform.db import create_engine, create_session_factory, tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from sqlalchemy import delete, select

from identity.api.auth import Actor
from identity.models import AccountReview, AccountReviewCommand, Outbox
from identity.schemas.account_review import AccountDecision
from identity.services.account_review import decide
from tests.factories import build_account_review


@pytest.mark.mysql
async def test_native_review_competition_and_intent_audit_rollback(mysql_url):
    engine = create_engine(mysql_url)
    factory = create_session_factory(engine)
    tenant_id = uuid7()
    with tenant_scope(tenant_id):
        try:
            async with factory() as db, db.begin():
                row = build_account_review(tenant_id=tenant_id)
                db.add(row)
                await db.flush()
                account_id = row.id

            with pytest.raises(RuntimeError, match="rollback proof"):
                async with factory() as db, db.begin():
                    await decide(
                        db,
                        Actor(tenant_id, uuid7()),
                        account_id,
                        AccountDecision(action="reject", version=1, reason="Rollback proof"),
                        secrets.token_hex(16),
                    )
                    raise RuntimeError("rollback proof")
            async with factory() as db:
                assert not list(await db.scalars(select(AccountReviewCommand)))
                assert not list(
                    await db.scalars(select(Outbox).where(Outbox.tenant_id == tenant_id))
                )
                assert (await db.get(AccountReview, account_id)).version == 1

            async def competing_decision(action):
                try:
                    async with factory() as db, db.begin():
                        await decide(
                            db,
                            Actor(tenant_id, uuid7()),
                            account_id,
                            AccountDecision(
                                action=action,
                                version=1,
                                reason="Concurrent proof",
                                attested=action == "approve",
                            ),
                            secrets.token_hex(16),
                        )
                    return "accepted"
                except ConflictError:
                    return "conflict"

            assert sorted(
                await asyncio.gather(competing_decision("approve"), competing_decision("reject"))
            ) == ["accepted", "conflict"]
            async with factory() as db:
                assert len(list(await db.scalars(select(AccountReviewCommand)))) == 1
                assert (
                    len(list(await db.scalars(select(Outbox).where(Outbox.tenant_id == tenant_id))))
                    == 1
                )
                assert (await db.get(AccountReview, account_id)).version == 2
        finally:
            async with factory() as db, db.begin():
                await db.execute(
                    delete(AccountReviewCommand).where(AccountReviewCommand.tenant_id == tenant_id)
                )
                await db.execute(delete(AccountReview).where(AccountReview.tenant_id == tenant_id))
                await db.execute(delete(Outbox).where(Outbox.tenant_id == tenant_id))
            await engine.dispose()

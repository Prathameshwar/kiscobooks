"""The live company configuration digest is the guard; the one stored at setup is not."""

import logging

from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from voucher_execution.transport import command_digest

from accounting.models.subledger import OpenItem
from tests.conftest import TENANT
from tests.test_invoice_execution import run
from tests.test_purchase_credit_scope import as_actor, poster, two_line_purchase

LOGGER = "accounting.voucher_execution"


async def test_a_command_whose_digest_differs_from_the_live_context_never_posts(
    client, app, caplog
):
    command = await two_line_purchase(client, app)
    stale = command.model_copy(update={"company_configuration_hash": "d" * 64})
    stale = stale.model_copy(update={"request_hash": command_digest(stale)})
    with caplog.at_level(logging.ERROR, logger=LOGGER):
        result = await run(app, as_actor(stale, poster()))
    assert (result.outcome, result.rejection_code) == ("REJECTED", "CONTENT_REJECTED")
    assert '"error_type":"ConflictError"' in caplog.text
    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count(OpenItem.id))) == 0
    # The same bill with the live digest posts.
    assert (await run(app, as_actor(command, poster(), fresh_identity=True))).outcome == "COMMITTED"

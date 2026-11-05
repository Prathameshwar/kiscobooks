import pytest
from billing_platform.db import tenant_scope
from billing_platform.db.platform_models import Outbox
from conftest import COMPANY, TENANT
from sqlalchemy import select
from test_source_versions import staged

from reports.models.core import ReportGeneration
from reports.models.source_versions import ReportSourceCut
from reports.tasks import source_publication as publication


async def test_publication_restart_reuses_frozen_verification_without_exposing_partial_source(
    app, monkeypatch
):
    (_, _, identity), _ = await staged(app)
    original = publication.immutable_claim

    def crash(*args):
        raise RuntimeError("claim publication interrupted")

    with tenant_scope(TENANT):
        async with app.state.session_factory() as db:
            cut = await db.scalar(
                select(ReportSourceCut).where(ReportSourceCut.generation_id == identity)
            )
        monkeypatch.setattr(publication, "immutable_claim", crash)
        with pytest.raises(RuntimeError, match="interrupted"):
            await publication.publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            assert (await db.get(ReportGeneration, identity)).status == "BUILDING"
            assert (await db.get(ReportSourceCut, cut.id)).verification is not None
            assert (
                await db.scalar(
                    select(Outbox.id).where(
                        Outbox.aggregate_id == cut.id,
                        Outbox.event_type == "reports.report.verified",
                    )
                )
                is not None
            )
        monkeypatch.setattr(publication, "immutable_claim", original)

        async def reject_reverification(*args):
            raise AssertionError("retained immutable verification should survive publication retry")

        monkeypatch.setattr(publication, "verify", reject_reverification)
        await publication.publish(app.state.session_factory, COMPANY, cut.id)
        await publication.publish(app.state.session_factory, COMPANY, cut.id)
        async with app.state.session_factory() as db:
            assert (await db.get(ReportGeneration, identity)).status == "READY"

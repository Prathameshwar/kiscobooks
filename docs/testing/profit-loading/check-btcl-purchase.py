"""Read only: bounded BTCL Purchase configuration and section counts."""
import asyncio
import json
import os
import uuid

from billing_platform.db import tenant_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from vouchers.models.core import Voucher, VoucherLine, VoucherRevision, VoucherType, VoucherTypeRevision
from vouchers.models.invoice import VoucherChargeDetail, VoucherInvoiceDetail, VoucherSupplyDetail, VoucherSupplyTaxContext


async def main():
    company = uuid.UUID('01a1b1b1-9d87-7750-8ae4-62f2d18f8270')
    tenant = uuid.UUID('01a1ab0d-8808-7153-b0e8-747586be1ad0')
    voucher_id = uuid.UUID('01a1b45b-9303-7215-85b8-2885c665a15c')
    engine = create_async_engine(os.environ['VOUCHERS_DATABASE_URL'], echo=False)
    with tenant_scope(tenant):
        async with async_sessionmaker(engine)() as db:
            voucher = await db.scalar(select(Voucher).where(Voucher.company_id == company, Voucher.id == voucher_id))
            revision = await db.scalar(select(VoucherRevision).where(VoucherRevision.company_id == company, VoucherRevision.voucher_id == voucher_id, VoucherRevision.revision_number == voucher.current_revision))
            kind = await db.scalar(select(VoucherType).where(VoucherType.company_id == company, VoucherType.id == voucher.type_id))
            types = list(await db.scalars(select(VoucherTypeRevision).where(VoucherTypeRevision.company_id == company, VoucherTypeRevision.type_id == kind.id).order_by(VoucherTypeRevision.revision_number.desc()).limit(3)))
            print('VOUCHER', json.dumps({'status': voucher.status, 'revision': voucher.current_revision, 'type_revision_id': str(revision.type_revision_id), 'type_current_revision': kind.current_revision}))
            for row in types:
                print('TYPE_POLICY', json.dumps({'revision': row.revision_number, 'bound_to_bill': row.id == revision.type_revision_id, 'policy': row.policy}))
            print('SAVED_DEFINITION', json.dumps(revision.definition_snapshot))
            for model in (VoucherLine, VoucherSupplyDetail, VoucherChargeDetail, VoucherSupplyTaxContext):
                count = await db.scalar(select(func.count(model.id)).where(model.company_id == company, model.revision_id == revision.id))
                print('SECTION_COUNT', model.__tablename__, count)
            invoice = await db.scalar(select(VoucherInvoiceDetail).where(VoucherInvoiceDetail.company_id == company, VoucherInvoiceDetail.revision_id == revision.id))
            print('INVOICE', json.dumps({'exists': invoice is not None, 'profile': invoice.profile if invoice else None, 'registered': bool(invoice and invoice.company_registration_id), 'accepted': bool(invoice and invoice.accepted_calculation_hash)}))
    await engine.dispose()


asyncio.run(main())

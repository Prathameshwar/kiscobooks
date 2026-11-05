'use client';
import { Button, ErrorState, Notice, PageNavigation } from '@janso/ui';
import { useVoucherType } from '../lib/voucher-types';
import { areaHref, familyHref, listHref, workflowLabel, type OperateArea, type OperateFamily } from '../lib/operate-navigation';
import { VoucherDirectory } from './VoucherDirectory';

export function OperateVoucherList({ company, permissions, area, family, kind, typeId }: { company: string; permissions: readonly string[]; area: OperateArea; family: OperateFamily; kind: string; typeId?: string }) {
  const type = useVoucherType(company, typeId);
  const title = type.data?.name ?? type.data?.code ?? workflowLabel(area, kind);
  const mismatch = !!typeId && !!type.data && type.data.kind !== kind;
  return <div className="janso-page">
    <PageNavigation back={{ href: familyHref(area, family), label: family.title.toLowerCase() }} breadcrumbs={[{ label: area.title, href: areaHref(area) }, { label: family.title, href: familyHref(area, family) }, { label: title }]} />
    {typeId && type.loading ? <p role="status">Loading voucher type…</p> : type.failure ? <Notice tone="warning">{type.failure.message} <Button variant="ghost" onClick={type.refresh}>Retry voucher type</Button></Notice>
      : mismatch ? <ErrorState status={403} detail="This voucher type belongs to another workflow." />
        : !typeId || type.data ? <VoucherDirectory key={company + kind + (typeId ?? '')} company={company} permissions={permissions} scope={{ kind, typeId, title, href: listHref(area, family, kind, typeId) }} /> : null}
  </div>;
}

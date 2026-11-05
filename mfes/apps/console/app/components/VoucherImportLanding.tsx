'use client';
import { ActionCard, Card, CardBody, Notice, PageHeader, PageNavigation, ReceiptIcon } from '@janso/ui';
import { IMPORT_KINDS, operateReturn, withReturn } from '../lib/operate-navigation';
import { kindLabel } from '../lib/voucher-kinds';
import { VoucherImport } from './VoucherImport';

export function VoucherImportLanding({ company, permissions, kind, typeId, returnTo }: { company: string; permissions: readonly string[]; kind?: string; typeId?: string; returnTo?: string }) {
  const back = operateReturn(returnTo);
  const supported = !kind || Object.hasOwn(IMPORT_KINDS, kind);
  return <div className="janso-page">
    <PageNavigation back={{ href: back ?? '/vouchers', label: back ? 'voucher list' : 'voucher drafts' }} />
    <PageHeader title={kind ? 'Import ' + kindLabel(kind).toLowerCase() + ' vouchers' : 'Import vouchers'} lede="Download a template, validate your file and review the results before creating drafts." />
    {supported ? <Card><CardBody><VoucherImport company={company} permissions={permissions} initialKind={kind} initialTypeId={typeId} /></CardBody></Card> : <>
      <Notice>File import is currently available for sales, purchase, notes, receipts, payments, contra and journals. {kindLabel(kind!)} vouchers can be entered through New voucher.</Notice>
      {permissions.includes('vouchers.create') && <a className="janso-btn janso-btn--primary" href={withReturn('/vouchers/entry?kind=' + kind, back)}>New voucher</a>}
      <div className="janso-action-card-grid janso-action-card-grid--compact">{Object.entries(IMPORT_KINDS).map(([value, label]) => <ActionCard key={value} title={label} description="Open the file import workflow." icon={<ReceiptIcon />} href={withReturn('/vouchers/import?kind=' + value, back)} actionLabel="Import vouchers" />)}</div>
    </>}
  </div>;
}

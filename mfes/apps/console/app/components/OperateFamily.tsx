'use client';
import { useCallback, useEffect, useState } from 'react';
import { ActionCard, Button, DocumentIcon, FilterBar, Notice, PageHeader, PageNavigation, Pager, ReceiptIcon, SectionHeader, TableSearch } from '@janso/ui';
import { GENERIC_PURCHASE_TYPE, useVoucherTypes, type VoucherTypeItem } from '../lib/voucher-types';
import { kindSlug, kindSummary } from '../lib/voucher-kinds';
import { areaHref, cardMatches, familyHref, listHref, withReturn, workflowLabel, type OperateArea, type OperateFamily } from '../lib/operate-navigation';

function typeCardTitle(kind: string, row: VoucherTypeItem): string | null {
  const name = row.name?.trim() || row.code || row.id;
  if (kind === 'SALES' && (!row.profile || row.profile === 'STANDARD') && /^sales\s*(?:[-–—]\s*)?mixed\s+invoice$/i.test(name)) return 'Sales - Product & Account Invoice';
  if (kind !== 'PURCHASE') return name;
  if (GENERIC_PURCHASE_TYPE.test(name)) return null;
  return /^purchase\s*(?:[-–—]\s*)?mixed\s+bill$/i.test(name)
    ? 'Purchase - Goods & Services Bill' : name;
}

const salesCards: Record<string, { section: string; summary: string; all: string }> = {
  SALES: { section: 'Sales invoices', summary: 'Customer invoices and preliminary pro forma documents.', all: 'All Sales Invoices' },
  CREDIT_NOTE: { section: 'Customer returns & credits', summary: 'Customer returns, credit notes and invoice adjustments.', all: 'All Returns & Credit Notes' },
  SALES_ORDER: { section: 'Orders & quotations', summary: 'Customer quotations and confirmed orders.', all: 'All Orders & Quotations' },
  DELIVERY_NOTE: { section: 'Delivery notes & challans', summary: 'Customer deliveries, dispatch notes and challans.', all: 'All Delivery Notes & Challans' },
};
function typeCardDescription(area: OperateArea, family: OperateFamily, kind: string, row: VoucherTypeItem): string {
  if (area.key === 'income' && family.key === 'sales') {
    if (kind === 'CREDIT_NOTE') return 'Customer returns and credit adjustments. Product and account details follow this type’s settings.';
    if (kind === 'DELIVERY_NOTE') return 'Goods dispatched to customers. View saved delivery documents for this type.';
    if (kind === 'SALES_ORDER') return row.profile === 'QUOTATION' ? 'Customer price quotations before confirming an order.' : 'Customer orders to fulfil and invoice.';
    if (row.profile === 'PRO_FORMA') return 'Preliminary customer invoices. View pro forma documents for this type.';
    if (kind === 'SALES') {
      const name = row.name?.trim() ?? '';
      if (/^sales\s*(?:[-–—]\s*)?mixed\s+invoice$/i.test(name)) return 'Customer invoices with item and account details. Entry follows this type’s settings.';
      if (/^sales\s*(?:[-–—]\s*)?product\s+invoice$/i.test(name)) return 'Customer invoices for goods and services. Entry follows this type’s settings.';
      if (/^sales\s*(?:[-–—]\s*)?account\s+invoice$/i.test(name)) return 'Account-based customer invoices. Entry follows this type’s settings.';
    }
  }
  return area.key === 'expense' && kind === 'DEBIT_NOTE'
    ? 'Purchase returns and supplier adjustments. Product and account details follow this type’s settings.'
    : `Voucher type: ${row.code ?? row.id}. View saved vouchers for this type.`;
}

type KindCardsProps = { company: string; area: OperateArea; family: OperateFamily; kind: string; search: string; onResult: (kind: string, search: string, visible: boolean) => void };
type TypeResults = ReturnType<typeof useVoucherTypes>;
const relatedTitle = 'Returns, Notes & Receipts';
const hasSingleType = (types: TypeResults) => !types.loading && !types.failure && types.data?.items.length === 1
  && !types.hasPrevious && !types.data.page.has_more;

function KindCards(props: KindCardsProps) {
  const { company, kind } = props;
  const types = useVoucherTypes(company, { q: '', kind, status: 'ACTIVE' });
  return <KindCardResults {...props} types={types} />;
}
function KindCardResults({ area, family, kind, search, onResult, types, cardsOnly = false }: KindCardsProps & { types: TypeResults; cardsOnly?: boolean }) {
  const salesPage = area.key === 'income' && family.key === 'sales';
  const presentation = salesPage ? salesCards[kind] : undefined;
  const originalLabel = workflowLabel(area, kind);
  const label = presentation?.section ?? originalLabel;
  const summary = presentation?.summary ?? kindSummary(kind);
  const originalKindTitle = 'All ' + originalLabel + ' vouchers';
  const kindTitle = presentation?.all ?? originalKindTitle;
  const matchesKind = cardMatches(search, label, originalLabel, kindSummary(kind), kind, cardsOnly ? relatedTitle : undefined);
  const singleType = hasSingleType(types);
  const showKind = kind !== 'PURCHASE' && !types.loading && !singleType && cardMatches(search, kindTitle, originalKindTitle, label, originalLabel, kindSummary(kind), kind);
  const rows = (types.data?.items ?? []).flatMap(row => {
    const title = typeCardTitle(kind, row);
    return title && (showKind || matchesKind || cardMatches(search, title, row.name, row.code, salesPage ? typeCardDescription(area, family, kind, row) : undefined)) ? [{ row, title }] : [];
  });
  const visible = !!(showKind || rows.length || types.loading || types.failure || types.hasPrevious || types.data?.page.has_more || kind === 'PURCHASE' && !search);
  useEffect(() => { onResult(kind, search, visible); }, [kind, search, visible, onResult]);
  if (!visible) return null;
  const cards = <>
      {showKind && <ActionCard title={kindTitle} description="Browse all voucher types and statuses in this workflow." icon={<ReceiptIcon />} href={listHref(area, family, kind)} actionLabel="View vouchers" />}
      {rows.map(({ row, title }) => <ActionCard key={row.id} title={title} description={typeCardDescription(area, family, kind, row)} icon={<ReceiptIcon />} href={listHref(area, family, kind, row.id)} actionLabel="View type vouchers" />)}
  </>;
  if (cardsOnly) return cards;
  return <section className="janso-flow" aria-label={label}>
    <SectionHeader title={label} description={summary} />
    <div className="janso-action-card-grid janso-action-card-grid--compact">{cards}</div>
    {types.loading && <p role="status">Loading {label.toLowerCase()} voucher types…</p>}
    {types.failure && <Notice tone="warning">{types.failure.message} <Button variant="ghost" onClick={types.first}>Retry {label.toLowerCase()} types</Button></Notice>}
    {!types.loading && !types.failure && !search && kind === 'PURCHASE' && !rows.length && <p>No specific purchase bill types to display.</p>}
    {!types.loading && !types.failure && kind !== 'PURCHASE' && !types.data?.items.length && <p>No active voucher types are configured. The voucher list still includes saved vouchers.</p>}
    {!types.loading && !types.failure && search && !showKind && !rows.length && <p>No matching types on this page.</p>}
    {!types.failure && (types.hasPrevious || types.data?.page.has_more) && <>
      <Notice>Search matches names and codes on this page of types. Browse other pages for more types.</Notice>
      <Pager noun="voucher type" count={types.data?.items.length ?? 0} limit={types.limit} busy={types.loading} hasPrevious={types.hasPrevious} hasNext={!!types.data?.page.has_more} onPrevious={types.previous} onNext={types.next} onLimitChange={types.setLimit} />
    </>}
  </section>;
}
function PurchaseRelatedCards(props: Omit<KindCardsProps, 'kind'>) {
  const debit = useVoucherTypes(props.company, { q: '', kind: 'DEBIT_NOTE', status: 'ACTIVE' });
  const credit = useVoucherTypes(props.company, { q: '', kind: 'CREDIT_NOTE', status: 'ACTIVE' });
  const receipt = useVoucherTypes(props.company, { q: '', kind: 'RECEIPT_NOTE', status: 'ACTIVE' });
  const entries = [{ kind: 'DEBIT_NOTE', types: debit }, { kind: 'CREDIT_NOTE', types: credit }, { kind: 'RECEIPT_NOTE', types: receipt }];
  const grouped = entries.filter(entry => hasSingleType(entry.types));
  const visible = grouped.some(({ kind, types }) => {
    const row = types.data?.items[0];
    return cardMatches(props.search, relatedTitle, workflowLabel(props.area, kind), kindSummary(kind), kind, row && typeCardTitle(kind, row), row?.name, row?.code);
  });
  return <>
    <section className={visible ? 'janso-flow' : undefined} aria-label={relatedTitle} hidden={!visible}>
      <SectionHeader title={relatedTitle} description="Purchase returns, supplier debit and credit notes, and goods receipt notes." />
      <div className="janso-action-card-grid janso-action-card-grid--compact">{grouped.map(({ kind, types }) => <KindCardResults key={kind} {...props} kind={kind} types={types} cardsOnly />)}</div>
    </section>
    {entries.filter(entry => !hasSingleType(entry.types)).map(({ kind, types }) => <KindCardResults key={kind} {...props} kind={kind} types={types} />)}
  </>;
}
export function OperateFamilyPage({ company, area, family, canPrint, canManageTypes }: { company: string; area: OperateArea; family: OperateFamily; canPrint: boolean; canManageTypes: boolean }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<Record<string, { search: string; visible: boolean }>>({});
  const onResult = useCallback((kind: string, search: string, visible: boolean) => {
    setResults(previous => previous[kind]?.search === search && previous[kind]?.visible === visible ? previous : { ...previous, [kind]: { search, visible } });
  }, []);
  const back = familyHref(area, family);
  const isPurchase = area.key === 'expense' && family.key === 'purchase';
  const prints = family.kinds.filter(kind => cardMatches(search, workflowLabel(area, kind) + ' print config', workflowLabel(area, kind), kindSummary(kind), 'print configuration'));
  return <div className="janso-page">
    <PageNavigation back={{ href: areaHref(area), label: area.title.toLowerCase() }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: area.title, href: areaHref(area) }, { label: family.title }]} />
    <PageHeader title={family.title} lede={family.description + ' Open a voucher list or choose a company voucher type.'} actions={canManageTypes ? <a className="janso-btn janso-btn--ghost" href="/masters/voucher-types">Manage voucher types</a> : undefined} />
    <FilterBar><TableSearch label="Search workflow cards" placeholder="Search vouchers, type names, codes or print settings" value={search} onChange={setSearch} minLength={0} maxLength={100} hint="Type names and codes are searched on each displayed page." /></FilterBar>
    {search && family.kinds.every(kind => results[kind]?.search === search && !results[kind]?.visible) && (!canPrint || !prints.length) && <Notice>No cards match your search. Clear the search to see all vouchers and types.</Notice>}
    {family.kinds.map(kind => isPurchase && kind === 'DEBIT_NOTE'
      ? <PurchaseRelatedCards key={kind} company={company} area={area} family={family} search={search} onResult={onResult} />
      : isPurchase && (kind === 'CREDIT_NOTE' || kind === 'RECEIPT_NOTE') ? null
      : <KindCards key={kind} company={company} area={area} family={family} kind={kind} search={search} onResult={onResult} />)}
    {canPrint && <section className="janso-flow" aria-label="Print configuration">
      <SectionHeader title="Print configuration" description="View or customise the layout used by each voucher kind." />
      {!prints.length && <Notice>No print settings match your search.</Notice>}
      <div className="janso-action-card-grid janso-action-card-grid--compact">{prints.map(kind => <ActionCard key={kind} title={workflowLabel(area, kind) + ' print config'} description="Standard layout, custom templates and print routing." icon={<DocumentIcon />} actionLabel="Open print settings" href={withReturn('/documents/vouchers/' + kindSlug(kind), back)} />)}</div>
    </section>}
  </div>;
}

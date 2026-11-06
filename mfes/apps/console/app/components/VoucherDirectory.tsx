'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, DataTable, EM_DASH, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import { voucherCommandRequest } from '../lib/voucher-fields';
import { useServiceList } from '../lib/service-resource';
import { stockRequest } from '../lib/stock';
import { trackingId } from '../lib/stock-tracking-resources';
import { newVoucherHref, withReturn } from '../lib/operate-navigation';
import { purchasePrintAction } from '../lib/purchase-print-action';

type Row = components['schemas']['ResourceItem'];

/**
 * The counterparty's display name, resolved per row from Accounting's own authorized account
 * read — never replicated into Vouchers (it deliberately keeps no party names; see
 * `apis/accounting/src/accounting/api/voucher_sources.py`). Looked up once per account id seen
 * on this page and cached for the component's lifetime.
 */
function useCounterpartyNames(company: string, accountIds: readonly string[]) {
  const [names, setNames] = useState<Map<string, string>>(new Map());
  const cache = useRef(names);
  cache.current = names;
  useEffect(() => {
    const pending = Array.from(new Set(accountIds.filter(id => trackingId.test(id) && !cache.current.has(id))));
    if (!pending.length) return;
    let alive = true;
    (async () => {
      // Bounded fan-out: a page holds at most 200 rows, never one call per row at once.
      for (let offset = 0; offset < pending.length; offset += 5) {
        const batch = await Promise.all(pending.slice(offset, offset + 5).map(async id => {
          try {
            const account = await stockRequest<{ id: string; company_id: string; name?: string | null; code?: string | null }>({ path: `/v1/companies/${company}/accounts/${id}` });
            return account.id === id && account.company_id === company ? [id, account.name ?? account.code ?? id] as const : null;
          } catch { return null; }
        }));
        if (!alive) return;
        setNames(current => {
          const next = new Map(current);
          for (const row of batch) if (row) next.set(row[0], row[1]);
          return next;
        });
      }
    })();
    return () => { alive = false; };
  }, [company, accountIds.join(',')]);
  return names;
}

export type VoucherListScope = { kind: string; typeId?: string; title: string; href: string };
export function VoucherDirectory({ company, permissions, scope }: { company: string; permissions: readonly string[]; scope?: VoucherListScope }) {
  const [q, setQuery] = useState(''), [status, setStatus] = useState(scope ? '' : 'DRAFT');
  const filters = new URLSearchParams({ status, ...(q.trim() ? { q: q.trim() } : {}) });
  if (!status) filters.delete('status');
  if (scope) { filters.set('kind', scope.kind); if (scope.typeId) filters.set('type_id', scope.typeId); }
  const read = useServiceList<Row>(`/v1/companies/${company}/vouchers`, filters.toString(), voucherCommandRequest, row => {
    if (!trackingId.test(row.id) || row.company_id !== company || !Number.isSafeInteger(row.row_version) || row.row_version < 1 || scope && (row.kind !== scope.kind || scope.typeId && row.type_id !== scope.typeId)) throw { status: 502, message: 'The voucher list could not be verified for this company.' };
  });
  const names = useCounterpartyNames(company, (read.data?.items ?? []).map(row => row.party_account_id).filter((id): id is string => !!id));
  const columns: Column<Row>[] = [
    { key: 'document_date', header: 'Date', type: 'date' },
    { key: 'type_code', header: 'Voucher type', type: 'text' },
    { key: 'ref_number', header: 'Ref number', type: 'text' },
    { key: 'party_account_id', header: 'Name', type: 'custom', render: row => row.party_account_id ? names.get(row.party_account_id) ?? row.party_account_id : EM_DASH },
    { key: 'amount', header: 'Amount', type: 'money', currencyKey: 'currency' },
    { key: 'status', header: 'Status', type: 'status' },
  ];
  const canCreate = permissions.includes('vouchers.create'), canEdit = permissions.includes('vouchers.edit');
  const isPurchase = (row: Row) => row.kind === 'PURCHASE' && row.profile === 'STANDARD';
  const editorAvailable = (row: Row) => ['JOURNAL', 'CONTRA', 'RECEIPT', 'PAYMENT'].includes(row.kind ?? '') || isPurchase(row);
  // Purchase editing uses its one entry screen. Saving a submitted or approved bill reopens a draft revision.
  const editLink = (row: Row) => isPurchase(row) ? '/vouchers/new/purchase?voucher_id=' + row.id + '&type_id=' + row.type_id : `/vouchers/${row.id}/edit?type_id=${row.type_id}`;
  const rowActions = (row: Row) => {
    const print = isPurchase(row) ? purchasePrintAction({
      saved: row.revision_id ? { id: row.id, revisionId: row.revision_id, version: row.row_version } : null,
      permitted: permission => permissions.includes(permission),
      dirty: false, uncertain: false, busy: false, executing: false, editorOpen: false,
    }) : { kind: 'hidden' } as const;
    return [
      { id: 'review', label: 'Review voucher', href: withReturn('/vouchers/' + row.id, scope?.href) },
      ...(canEdit && editorAvailable(row) && (row.status === 'DRAFT' || isPurchase(row) && ['REJECTED', 'SUBMITTED', 'APPROVED'].includes(row.status ?? '')) && trackingId.test(row.type_id ?? '')
        ? [{ id: 'edit', label: row.status === 'DRAFT' ? 'Edit draft' : `Edit ${row.status?.toLowerCase()} bill`, href: withReturn(editLink(row), scope?.href) }] : []),
      ...(print.kind === 'ready' ? [{ id: 'print', label: 'Print / PDF', href: print.href }] : []),
    ];
  };
  const selection = scope ? '?' + new URLSearchParams({ kind: scope.kind, ...(scope.typeId ? { type_id: scope.typeId } : {}) }) : '';
  return <section className={scope ? 'janso-flow' : 'janso-page'}>
    <PageHeader title={scope ? scope.title + ' vouchers' : 'Voucher drafts'} lede="Find a saved voucher, review its details and continue its workflow." actions={<>
      {canCreate && <a className="janso-btn janso-btn--primary" href={newVoucherHref(scope?.kind, scope?.typeId, scope?.href)}>{scope ? 'New voucher' : 'Create voucher draft'}</a>}
      {permissions.includes('vouchers.import.read') && <a className="janso-btn janso-btn--ghost" href={withReturn('/vouchers/import' + selection, scope?.href)}>Import voucher</a>}
    </>} />
    {!canCreate && <Notice>Read-only access. Voucher creation permission is required to add a voucher.</Notice>}
    <FilterBar actions={<Button variant="ghost" onClick={read.first} disabled={read.loading}>{scope ? 'Refresh vouchers' : 'Refresh drafts'}</Button>}>
      <TableSearch label="Search voucher number" placeholder="Voucher number starts with or voucher ID" hint="Search an issued number prefix or a complete voucher ID." value={q} minLength={1} maxLength={100} onChange={setQuery} busy={read.loading} />
      <Select label="Status" value={status} onChange={setStatus} options={[{ value: '', label: 'All statuses' }, ...['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'ISSUED', 'POSTED', 'CANCELLED', 'REVERSED', 'ACCEPTED', 'DECLINED', 'EXPIRED'].map(value => ({ value, label: value.toLowerCase() }))]} />
    </FilterBar>
    {read.failure && <Notice tone="warning">{read.failure.message}</Notice>}
    <Card><DataTable caption="Saved company vouchers" columns={columns} rows={read.data?.items ?? []} rowId={row => row.id} loading={read.loading} error={read.failure ? read.failure.status === 401 ? 401 : read.failure.status === 403 ? 403 : 500 : null} emptyTitle="No saved vouchers match" onRetry={read.first}
      rowActions={rowActions} />
      {!read.failure && <Pager noun="voucher" count={read.data?.items.length ?? 0} limit={read.limit} busy={read.loading} hasPrevious={read.hasPrevious} hasNext={!!read.data?.page.has_more} onPrevious={read.previous} onNext={read.next} onLimitChange={read.setLimit} />}
    </Card>
  </section>;
}

'use client';
import { useEffect, useMemo, useState } from 'react';
import { Button, Card, CardBody, DataTable, Notice, Pager, SearchIcon, SearchSelect, SectionHeader, Select, TextField, useFormatters, type Column } from '@janso/ui';
import { accountingRequest } from '../lib/accounting-configuration';
import { useServiceList, useServiceRead } from '../lib/service-resource';
import { lookup } from '../lib/voucher-fields';
import { owned, type Declaration, type Entry, type Metadata } from '../lib/financial-opening';
import { accountFilters, canCaptureOpening, changeAccountOpening, OFFSET_SOURCE, type OpeningAccount, type OpeningCategory } from '../lib/financial-opening-worksheet';
import { AccountingFailure } from './AccountingConfigurationCommon';

export function FinancialOpeningSelection({ company, category, group, disabled, onCategory, onGroup }: {
  company: string; category: OpeningCategory; group: string | null; disabled: boolean;
  onCategory: (value: OpeningCategory) => void; onGroup: (value: string | null) => void;
}) {
  const selectedGroup = useServiceRead<{ id: string; company_id: string; name?: string; code?: string }>(group ? `/v1/companies/${company}/account-groups/${group}` : undefined, accountingRequest, row => {
    owned(company)(row); if (row.id !== group) throw { status: 502, message: 'The selected account group could not be verified.' };
  });
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Choose accounts" description="Start with a category. You can return to add other categories before posting; your entries stay in the worksheet." />
    <fieldset className="janso-opening-choices" disabled={disabled}><legend className="janso-visually-hidden">Account category</legend>
      {([['BUYER', 'Buyer', 'Customer balances'], ['SUPPLIER', 'Supplier', 'Supplier balances'], ['OTHER', 'Other Accounts', 'Accounts in one group']] as const).map(([id, label, hint]) =>
        <label key={id} className="janso-opening-choice" data-selected={category === id}><input type="radio" name="opening-category" value={id} checked={category === id} onChange={() => onCategory(id)} /><span><strong>{label}</strong><span className="janso-caption">{hint}</span></span></label>)}
    </fieldset>
    {category === 'OTHER' && <><SearchSelect label="Account group" required minQueryLength={0} scopeKey={company + ':opening-group'} loadOptions={lookup(company, 'account-groups')} value={group} selected={selectedGroup.data ? { id: selectedGroup.data.id, label: selectedGroup.data.name ?? selectedGroup.data.code ?? 'Selected group' } : undefined} disabled={disabled} onChange={onGroup} /><AccountingFailure failure={selectedGroup.failure} retry={selectedGroup.refresh} /></>}
  </div></CardBody></Card>;
}

export function FinancialOpeningAccounts(props: {
  company: string; category: OpeningCategory; group: string | null; value: Declaration; metadata: Metadata;
  disabled: boolean; onChange: (rows: Entry[]) => void; onDetails: (account: OpeningAccount, row?: Entry) => void;
}) {
  const format = useFormatters();
  const [search, setSearch] = useState(''), [query, setQuery] = useState('');
  useEffect(() => { const timer = setTimeout(() => setQuery(search), 250); return () => clearTimeout(timer); }, [search]);
  const filters = accountFilters(props.category, props.group, query);
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Enter opening balances" description="Accounts are listed A–Z. Leave blank for no opening. Your entries stay when you search or change pages." />
    <div className="janso-opening-toolbar"><TextField label="Quick account search" type="search" leading={<SearchIcon size={16} />} placeholder="Search by name or code" value={search} maxLength={160} hint={search.trim().length === 1 ? 'Enter at least two characters to search.' : undefined} onChange={event => setSearch(event.target.value)} /><p>All openings use <strong>{format.date(props.value.posting_date)}</strong></p></div>
    <AccountPage key={props.company + ':' + filters} {...props} filters={filters} />
    <p className="janso-caption">Buyer and supplier balances entered here are on account, with unknown bill dates. Use Details to enter historical bills or foreign-currency values.</p>
  </div></CardBody></Card>;
}

function AccountPage({ company, filters, value, metadata, disabled, onChange, onDetails }: Parameters<typeof FinancialOpeningAccounts>[0] & { filters: string }) {
  const list = useServiceList<OpeningAccount>(`/v1/companies/${company}/accounts`, filters, accountingRequest, owned(company));
  const rows = list.failure ? [] : list.data?.items ?? [];
  const byAccount = useMemo(() => {
    const index = new Map<string, Entry[]>();
    for (const entry of value.entries) index.set(entry.account_id, [...(index.get(entry.account_id) ?? []), entry]);
    return index;
  }, [value.entries]);
  const current = (account: OpeningAccount) => byAccount.get(account.id) ?? [];
  const editable = (account: OpeningAccount) => !disabled && account.status === 'ACTIVE' && !!account.kind && !!account.currency_mode && canCaptureOpening(metadata, account.kind === 'PARTY') && current(account).length <= 1 && current(account)[0]?.source_key !== OFFSET_SOURCE;
  const change = (account: OpeningAccount, patch: Pick<Partial<Entry>, 'amount' | 'side'>) => { if (editable(account)) onChange(changeAccountOpening(value, account, patch)); };
  const columns: Column<OpeningAccount>[] = [
    { type: 'custom', key: 'name', header: 'Account', render: row => <div className="janso-opening-account"><strong>{row.name ?? row.code ?? 'Restricted account'}</strong><span className="janso-caption">{row.code}{current(row).length > 1 ? ' · Multiple opening lines' : ''}</span></div> },
    { type: 'custom', key: 'amount', header: 'Opening', render: row => <TextField label={`Opening for ${row.name ?? row.code}`} inputMode="decimal" value={current(row)[0]?.amount ?? ''} placeholder="0.00" disabled={!editable(row)} onChange={event => change(row, { amount: event.target.value })} /> },
    { type: 'custom', key: 'side', header: 'Opening type', render: row => <Select label={`Opening type for ${row.name ?? row.code}`} value={current(row)[0]?.side ?? (row.party_role === 'SUPPLIER' ? 'CREDIT' : 'DEBIT')} disabled={!editable(row) || current(row)[0]?.documents?.some(document => document.document_kind !== 'ON_ACCOUNT')} options={[{ value: 'DEBIT', label: 'Dr' }, { value: 'CREDIT', label: 'Cr' }]} onChange={side => change(row, { side: side as Entry['side'] })} /> },
    { type: 'custom', key: 'date', header: 'Opening date', render: row => <TextField label={`Opening date for ${row.name ?? row.code}`} type="date" value={value.posting_date} readOnly /> },
    { type: 'custom', key: 'details', header: 'Details', render: row => <Button variant="ghost" disabled={disabled || !row.kind || current(row).length > 1} onClick={() => onDetails(row, current(row)[0])}>Details<span className="janso-visually-hidden"> for {row.name ?? row.code}</span></Button> },
  ];
  return <><AccountingFailure failure={list.failure} retry={list.first} />
    <div className="janso-opening-grid"><DataTable caption="Account opening balances" columns={columns} rows={rows} loading={list.loading} rowId={row => row.id} rowLabel={row => row.name ?? row.code ?? 'Account'} emptyTitle="No matching accounts" emptyBody="Try another search or select a different account category or group." /></div>
    {rows.some(row => !row.kind || !row.currency_mode) && <Notice>Some account details are restricted. Opening inputs stay disabled until the required account fields are readable.</Notice>}
    <Pager count={rows.length} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun="account" />
  </>;
}

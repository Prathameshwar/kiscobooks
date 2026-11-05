'use client';

import { useState } from 'react';
import {
  Button,
  DataTable,
  ErrorState,
  FilterBar,
  Notice,
  PageHeader,
  PageNavigation,
  Pager,
  Select,
  TableSearch,
  type Column,
} from '@janso/ui';
import { TYPES_ROOT, typeHref, useVoucherTypes, voucherTypeRequest, type VoucherTypeItem } from '../lib/voucher-types';
import { VOUCHER_KINDS, kindLabel } from '../lib/voucher-kinds';
import type { components } from '@janso/api-client/vouchers';
import { useServiceCommand } from '../lib/service-resource';
import { useAccessDraft } from './AccessCommon';

const STATUSES = [
  { value: 'ACTIVE', label: 'Active' },
  { value: 'RETIRED', label: 'Retired' },
];

/**
 * Every voucher type the company has, with the two filters a list this size needs and the service's
 * one search — a code prefix.
 *
 * A *kind* (Sales, Receipt…) is what the platform defines; a *type* is the company's own named
 * flavour of one ("Retail sales", "Export sales"), with its own entry rules. This is where the
 * types are found, started and retired; what a type enforces is its own page.
 */
export function VoucherTypeDirectory({ company, canManage }: { company: string; canManage: boolean }) {
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const list = useVoucherTypes(company, { q: search, kind, status });
  const preparation = useServiceCommand(voucherTypeRequest, 'voucher defaults');
  const guard = useAccessDraft(preparation.uncertain, preparation.pending);
  const [prepared, setPrepared] = useState<components['schemas']['DefaultsResult'] | null>(null);
  const filtered = !!(search || kind || status);
  const rows = list.data?.items ?? [];

  async function prepare() {
    setPrepared(null);
    const result = await preparation.execute<components['schemas']['DefaultsResult']>({
      service: 'vouchers', method: 'POST', path: `/v1/companies/${company}/voucher-type-defaults/bootstrap`, body: {},
    }, value => {
      if (value.company_id !== company || value.status !== 'READY'
        || !Array.isArray(value.features) || typeof value.catalogue_version !== 'string'
        || ![value.created_count, value.updated_count, value.preserved_count, value.review_count].every(count => Number.isInteger(count) && count >= 0 && count <= 64)
        || value.review_count !== 0) throw { status: 502, message: 'The voucher defaults result could not be verified. Retry the same preparation.' };
    });
    if (result) { setPrepared(result); list.first(); }
  }

  const columns: Column<VoucherTypeItem>[] = [
    {
      key: 'name',
      header: 'Name',
      type: 'link',
      locked: true,
      value: (row) => row.name,
      href: (row) => typeHref(row.id),
    },
    { key: 'code', header: 'Code', type: 'code' },
    { key: 'kind', header: 'Kind', value: (row) => (row.kind ? kindLabel(row.kind) : null) },
    {
      key: 'profile',
      header: 'Profile',
      value: (row) => (row.profile ? row.profile.toLowerCase().replaceAll('_', ' ') : null),
    },
    { key: 'current_revision', header: 'Revision', align: 'end' },
    {
      key: 'status',
      header: 'Status',
      type: 'status',
      label: (code) => (code === 'ACTIVE' ? 'Active' : 'Retired'),
      tone: (code) => (code === 'ACTIVE' ? 'success' : 'neutral'),
    },
  ];

  if (list.failure && !filtered) {
    return (
      <div className="janso-page">
        <ErrorState status={list.failure.status === 403 ? 403 : 500} detail={list.failure.message} />
      </div>
    );
  }

  return (
    <div className="janso-page">
      <PageNavigation
        onNavigate={guard.leave}
        back={{ href: '/masters', label: 'masters' }}
        breadcrumbs={[{ label: 'Masters', href: '/masters' }, { label: 'Voucher types' }]}
      />
      <PageHeader
        title="Voucher types"
        lede="A voucher type is a named version of a kind of voucher — Retail sales, Export sales — with its own entry rules."
        actions={
          canManage ? (
            <>
            <Button variant="ghost" disabled={preparation.pending} loading={preparation.pending} onClick={() => void prepare()}>
              {preparation.uncertain ? 'Retry preparing default types' : 'Prepare default voucher types'}
            </Button>
            <a className="janso-btn janso-btn--primary" href={`${TYPES_ROOT}/new`} onClick={guard.leave}>
              New voucher type
            </a>
            </>
          ) : undefined
        }
      />
      {!canManage ? <Notice>Read-only access. The voucher type manage permission is required to create, change or retire a type.</Notice> : null}
      {canManage ? <p>Prepare missing default types for this company and update untouched starter rules. Your custom rules and retired types are preserved.</p> : null}
      {prepared ? <Notice tone="success">Default voucher types are ready: {prepared.created_count} created, {prepared.updated_count} updated, {prepared.preserved_count} preserved.</Notice> : null}
      {preparation.failure ? <Notice tone="danger">{preparation.failure.message}</Notice> : null}

      <FilterBar>
        <TableSearch
          label="Search voucher types"
          placeholder="Code starts with…"
          hint="Searches the start of the code."
          value={search}
          onChange={setSearch}
          minLength={1}
          maxLength={40}
          busy={list.loading}
        />
        <Select
          label="Kind"
          value={kind}
          placeholder="All kinds"
          options={VOUCHER_KINDS.map((entry) => ({ value: entry.value, label: kindLabel(entry.value) }))}
          onChange={setKind}
        />
        <Select label="Status" value={status} placeholder="Any status" options={STATUSES} onChange={setStatus} />
      </FilterBar>

      {list.failure ? (
        <Notice tone="danger">
          {list.failure.message}{' '}
          <Button variant="ghost" onClick={list.first}>
            Try again
          </Button>
        </Notice>
      ) : null}

      <DataTable
        caption="Voucher types"
        columns={columns}
        rows={rows}
        rowId={(row) => row.id}
        rowLabel={(row) => row.name ?? row.code ?? 'Voucher type'}
        loading={list.loading}
        emptyTitle={filtered ? 'No voucher type matches' : 'No voucher types yet'}
        emptyBody={
          filtered
            ? 'Clear a filter or search a shorter code to see more.'
            : canManage
              ? 'Create the first one to give a kind of voucher its own entry rules.'
              : 'None has been created for this company.'
        }
      />
      <Pager
        count={rows.length}
        limit={list.limit}
        hasPrevious={list.hasPrevious}
        hasNext={!!list.data?.page.has_more}
        onPrevious={list.previous}
        onNext={list.next}
        onLimitChange={list.setLimit}
        busy={list.loading || !!list.failure}
        noun="voucher type"
      />
      {guard.confirmation}
    </div>
  );
}

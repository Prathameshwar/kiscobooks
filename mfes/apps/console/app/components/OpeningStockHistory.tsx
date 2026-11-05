'use client';
import { useState } from 'react';
import { Button, Card, Checkbox, DataTable, Notice, Pager, useFormatters, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { openingBase, openingRequest, openingDownload, type Control, type OpeningAccess, type Manifest } from '../lib/opening-stock';
import { useServiceList } from '../lib/service-resource';
import { TrackingReference } from './StockTrackingCommon';
import { StockReference } from './VoucherStock';
import { AccountingFailure } from './AccountingConfigurationCommon';

export function OpeningStockHistory({
  company,
  control,
  access,
  initialItemId,
}: {
  company: string;
  control: Control;
  access: OpeningAccess;
  initialItemId?: string;
}) {
  const [item, setItem] = useState<string | null>(initialItemId ?? null),
    [warehouse, setWarehouse] = useState<string | null>(null),
    [reversed, setReversed] = useState(false),
    [revision, setRevision] = useState<Manifest | null>(null),
    [error, setError] = useState('');
  const format = useFormatters(),
    base = openingBase(company) + '/' + control.id;
  const filters = new URLSearchParams({ include_reversed: String(reversed) });
  if (item) filters.set('item_id', item);
  if (warehouse) filters.set('warehouse_id', warehouse);
  type Cohort = components['schemas']['OpeningCohort'];
  type Revision = components['schemas']['OpeningRevisionItem'];
  const rows = useServiceList<Cohort>(
    base + '/cohorts',
    filters.toString(),
    openingRequest,
  );
  const versions = useServiceList<Revision>(
    base + '/revisions',
    '',
    openingRequest,
  );
  const columns: Column<Cohort>[] = [
    {
      key: 'item_id',
      header: 'Product',
      type: 'custom',
      render: (row) => (
        <a className="janso-link" href={'/inventory/stock?item_id=' + row.item_id}>
          View stock
        </a>
      ),
    },
    {
      key: 'warehouse_id',
      header: 'Warehouse',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={'/masters/warehouses/' + row.warehouse_id}
        >
          View warehouse
        </a>
      ),
    },
    {
      key: 'quantity',
      header: 'Base quantity',
      type: 'custom',
      render: (row) => format.quantity(row.quantity),
    },
    {
      key: 'value',
      header: 'Carrying value',
      type: 'custom',
      render: (row) =>
        format.money(row.value, { display: 'none' }) + ' ' + row.currency,
    },
    {
      key: 'received_on',
      header: 'Original receipt',
      type: 'custom',
      render: (row) =>
        row.history_known && row.received_on
          ? format.date(row.received_on)
          : 'Unknown',
    },
    {
      key: 'reversed',
      header: 'Status',
      type: 'custom',
      render: (row) => (row.reversed ? 'Reversed' : 'Applied'),
    },
    {
      key: 'posting_id',
      header: 'Evidence',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={'/inventory/stock?view=movements&posting_id=' + row.posting_id}
        >
          Stock movements
        </a>
      ),
    },
  ];
  return (
    <div className="janso-flow">
      <AccountingFailure
        failure={rows.failure ?? versions.failure}
        retry={() => {
          rows.first();
          versions.first();
        }}
      />
      {error && <Notice tone="danger">{error}</Notice>}
      <Card>
        <div className="janso-form-grid">
          <TrackingReference
            company={company}
            resource="items"
            label="Product filter"
            value={item}
            onChange={setItem}
          />
          <StockReference
            company={company}
            resource="warehouses"
            label="Warehouse filter"
            value={warehouse}
            onChange={setWarehouse}
            disabled={false}
          />
          <Checkbox
            checked={reversed}
            onChange={(event) => setReversed(event.target.checked)}
          >
            Include reversed cohorts
          </Checkbox>
        </div>
        <DataTable
          caption="Applied opening cohorts"
          columns={columns}
          rows={rows.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => row.source_key}
          loading={rows.loading}
          emptyTitle="No applied opening cohorts"
          emptyBody="Cohorts appear after native opening vouchers are posted and confirmed."
        />
        <Pager
          count={rows.data?.items.length ?? 0}
          limit={rows.limit}
          busy={rows.loading}
          hasPrevious={rows.hasPrevious}
          hasNext={!!rows.data?.page.has_more}
          onPrevious={rows.previous}
          onNext={rows.next}
          onLimitChange={rows.setLimit}
          noun="cohort"
        />
        {access.export && (
          <Button
            variant="ghost"
            onClick={() =>
              void openingDownload(
                'accounting',
                base + '/export-ticket',
                company,
              ).catch((reason) => setError(String(reason.message)))
            }
          >
            Export company opening evidence
          </Button>
        )}
      </Card>
      <Card>
        <DataTable
          caption="Immutable worksheet revisions"
          columns={[
            {
              key: 'revision',
              header: 'Revision',
              type: 'custom',
              render: (row) => (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setRevision(null);
                    setError('');
                    void openingRequest<Manifest>({
                      path: `${base}/revisions/${row.id}`,
                    })
                      .then(setRevision)
                      .catch((reason) => setError(String(reason.message)));
                  }}
                >
                  Review revision {row.revision}
                </Button>
              ),
            },
            {
              key: 'created_at',
              header: 'Recorded',
              type: 'custom',
              render: (row) => format.date(row.created_at.slice(0, 10)),
            },
          ]}
          rows={versions.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => 'Revision ' + row.revision}
          loading={versions.loading}
        />
        <Pager
          count={versions.data?.items.length ?? 0}
          limit={versions.limit}
          busy={versions.loading}
          hasPrevious={versions.hasPrevious}
          hasNext={!!versions.data?.page.has_more}
          onPrevious={versions.previous}
          onNext={versions.next}
          onLimitChange={versions.setLimit}
          noun="revision"
        />
        {revision && !rows.failure && !versions.failure && (
          <details open>
            <summary>Historical worksheet evidence</summary>
            <p>
              {revision.reason} · {revision.lines?.length ?? 0} allocations ·{' '}
              {revision.currency}
            </p>
            <pre className="janso-preview__text">
              {JSON.stringify(revision, null, 2)}
            </pre>
          </details>
        )}
      </Card>
      <Notice>
        Posted balances cannot be edited here. Review the original voucher and
        its reversal workflow before replacing a worksheet. Closed periods,
        later stock and dependent claims can prevent corrections.
      </Notice>
    </div>
  );
}

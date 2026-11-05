'use client';

import { useState } from 'react';
import { Button, DataTable, Modal, Notice, Pager, TableSearch, useFormatters, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import { voucherCommandRequest } from '../../lib/voucher-fields';
import { useServiceList } from '../../lib/service-resource';
import { requestFailure } from '../../lib/service-call';
import { trackingId } from '../../lib/stock-tracking-resources';
import { layoutPreviewHref } from '../../lib/purchase-print';

type Row = components['schemas']['ResourceItem'];
type Detail = components['schemas']['VoucherDetail'];

/** The saved bill a preview prints: its identity, and what the person recognises it by. */
type Chosen = { id: string; revisionId: string; version: number; billReference: string | null; documentDate: string | null; status: string };

const verifyRow = (company: string) => (row: Row) => {
  if (!trackingId.test(row.id) || row.company_id !== company || row.kind !== 'PURCHASE') {
    throw { status: 502, message: 'The Purchase list could not be verified for this company.' };
  }
};

/**
 * Choosing the saved Purchase bill a design version is previewed on (plan R4).
 *
 * The company's Purchase vouchers, searched the way the voucher list searches them (an issued
 * number prefix or a whole voucher id). A list row does not carry the supplier's bill number or
 * the saved revision a print names, so choosing one reads that bill once and shows what was read
 * — the supplier's bill number, its date and status — before the preview is opened on exactly
 * that saved revision.
 */
export function SavedBillPicker({
  company,
  templateId,
  version,
  open,
  onClose,
}: {
  company: string;
  templateId: string;
  version: { id: string; versionNumber: number };
  open: boolean;
  onClose: () => void;
}) {
  const format = useFormatters();
  const [q, setQuery] = useState('');
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [reading, setReading] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const filters = new URLSearchParams({ kind: 'PURCHASE', ...(q.trim() ? { q: q.trim() } : {}) });
  const list = useServiceList<Row>(`/v1/companies/${company}/vouchers`, filters.toString(), voucherCommandRequest, verifyRow(company), open);

  async function choose(row: Row): Promise<void> {
    setFailure(null);
    setReading(row.id);
    try {
      const detail = await voucherCommandRequest<Detail>({ path: `/v1/companies/${company}/vouchers/${row.id}` });
      if (
        !detail || detail.id !== row.id || detail.company_id !== company || detail.kind !== 'PURCHASE' ||
        !trackingId.test(detail.revision_id ?? '') || !Number.isSafeInteger(detail.row_version) || detail.row_version < 1
      ) {
        throw { status: 502, message: 'The saved Purchase could not be verified for this company.' };
      }
      const invoice = detail.invoice as { bill_reference?: string | null } | null | undefined;
      setChosen({
        id: detail.id,
        revisionId: detail.revision_id,
        version: detail.row_version,
        billReference: invoice?.bill_reference ?? null,
        documentDate: detail.document_date ?? null,
        status: detail.status,
      });
    } catch (error) {
      const problem = requestFailure(error, 'voucher service');
      setFailure(
        problem.status === 403
          ? 'You do not have access to read this Purchase.'
          : problem.status === 401
            ? 'Your session has expired. Sign in again, then choose the bill.'
            : problem.message,
      );
    } finally {
      setReading(null);
    }
  }

  const columns: Column<Row>[] = [
    { key: 'document_date', header: 'Bill date', type: 'date' },
    { key: 'issue_number', header: 'Voucher no.', value: (row) => row.issue_number ?? 'Not numbered yet' },
    { key: 'type_code', header: 'Voucher type' },
    { key: 'status', header: 'Status', value: (row) => (row.status ?? '').toLowerCase() },
    {
      key: 'choose',
      header: 'Choose',
      hideHeader: true,
      type: 'custom',
      align: 'end',
      render: (row) => (
        <Button
          variant="ghost"
          disabled={reading !== null}
          loading={reading === row.id}
          aria-label={`Choose the Purchase dated ${row.document_date ? format.date(row.document_date) : 'without a date'}${row.issue_number ? `, number ${row.issue_number}` : ''}`}
          onClick={() => void choose(row)}
        >
          Choose
        </Button>
      ),
    },
  ];

  function close(): void {
    setChosen(null);
    setFailure(null);
    onClose();
  }

  return (
    <Modal
      open={open}
      title={`Preview version ${version.versionNumber} with a saved bill`}
      size="lg"
      busy={reading !== null}
      onClose={close}
      footer={
        <>
          <button type="button" className="janso-btn janso-btn--ghost" onClick={close}>
            Cancel
          </button>
          {chosen ? (
            <>
              <button type="button" className="janso-btn janso-btn--ghost" onClick={() => setChosen(null)}>
                Choose another bill
              </button>
              <a
                className="janso-btn janso-btn--primary"
                href={layoutPreviewHref({ templateId, designVersionId: version.id, voucherId: chosen.id, revisionId: chosen.revisionId, version: chosen.version })}
              >
                Open the preview
              </a>
            </>
          ) : null}
        </>
      }
    >
      <div className="janso-flow">
        <p className="janso-meta">
          The PDF is the bill printed on this saved version of the design, marked “Layout preview · not for use” on every
          page. It is not the bill’s print, and nothing about the bill or the design changes.
        </p>
        {failure ? <Notice tone="danger">{failure}</Notice> : null}
        {chosen ? (
          <dl className="janso-flow" aria-label="Chosen bill">
            <div>
              <dt className="janso-meta">Supplier bill number</dt>
              <dd>{chosen.billReference ?? 'Not recorded'}</dd>
            </div>
            <div>
              <dt className="janso-meta">Bill date</dt>
              <dd>{chosen.documentDate ? format.date(chosen.documentDate) : 'Not recorded'}</dd>
            </div>
            <div>
              <dt className="janso-meta">Status</dt>
              <dd>{chosen.status.toLowerCase()}</dd>
            </div>
          </dl>
        ) : (
          <>
            <TableSearch
              label="Search Purchase bills"
              placeholder="Voucher number starts with, or voucher ID"
              hint="Search an issued number prefix or a complete voucher ID."
              value={q}
              minLength={1}
              maxLength={100}
              onChange={setQuery}
              busy={list.loading}
            />
            <DataTable
              caption="Saved Purchase bills"
              columns={columns}
              rows={list.data?.items ?? []}
              rowId={(row) => row.id}
              loading={list.loading}
              error={list.failure ? (list.failure.status === 401 ? 401 : list.failure.status === 403 ? 403 : 500) : null}
              emptyTitle="No saved Purchase bills match"
              emptyBody="Save a Purchase bill first, or search for another number."
              onRetry={list.first}
            />
            {!list.failure ? (
              <Pager
                noun="bill"
                count={list.data?.items.length ?? 0}
                limit={list.limit}
                busy={list.loading}
                hasPrevious={list.hasPrevious}
                hasNext={!!list.data?.page.has_more}
                onPrevious={list.previous}
                onNext={list.next}
                onLimitChange={list.setLimit}
              />
            ) : null}
          </>
        )}
      </div>
    </Modal>
  );
}

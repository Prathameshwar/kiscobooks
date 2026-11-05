'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, DataTable, Notice, PageHeader, PageNavigation, ReviewList, Select, Skeleton, TextField, Pager, useFormatters, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { openingBase, openingRequest, owned, verifyControl, sum, validateAllocation, blockers, type Allocation, type Control, type Manifest, type OpeningAccess, type Readiness } from '../lib/opening-stock';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { OpeningStockEntry } from './OpeningStockEntry';
import { OpeningStockImports } from './OpeningStockImports';
import { OpeningStockHistory } from './OpeningStockHistory';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { useAccessDraft } from './AccessCommon';

export function OpeningStockWorkspace({
  company,
  currency,
  access,
  initialItemId,
}: {
  company: string;
  currency: string;
  access: OpeningAccess;
  initialItemId?: string;
}) {
  const [tab, setTab] = useState<
      'worksheet' | 'drafts' | 'completion' | 'history'
    >('worksheet'),
    [lines, setLines] = useState<Allocation[] | null>(null),
    [reason, setReason] = useState(''),
    [mode, setMode] = useState<Manifest['opening_mode']>('COMBINED'),
    [entryDirty, setEntryDirty] = useState(false),
    [draftDirty, setDraftDirty] = useState(false),
    [offset, setOffset] = useState(0),
    [pageSize, setPageSize] = useState(25),
    [confirm, setConfirm] = useState<
      'save' | 'zero' | 'adopt' | 'finalize' | 'reopen' | null
    >(null),
    [message, setMessage] = useState('');
  const base = openingBase(company),
    format = useFormatters();
  const readiness = useServiceRead<Readiness>(
    base + '/readiness',
    openingRequest,
    owned(company),
  );
  const id = readiness.data?.control_id;
  const control = useServiceRead<Control>(
    id ? base + '/' + id : undefined,
    openingRequest,
    verifyControl(company),
  );
  const manifest = useServiceRead<Manifest>(
    id ? base + '/' + id + '/manifest' : undefined,
    openingRequest,
    (value) => {
      if (
        !Array.isArray(value.lines) ||
        !value.currency ||
        value.stock_date !== readiness.data?.books_begin_date
      )
        throw {
          status: 502,
          message: 'The company worksheet could not be verified.',
        };
    },
  );
  const preview = useServiceRead<
    components['schemas']['OpeningAccountingPreview']
  >(
    id && tab === 'completion'
      ? base + '/' + id + '/accounting-preview'
      : undefined,
    openingRequest,
    owned(company),
  );
  const reconciliation = useServiceRead<Control>(
    id && tab === 'completion'
      ? base + '/' + id + '/reconciliation'
      : undefined,
    openingRequest,
    verifyControl(company),
  );
  const editVersion = useRef<{
    id: string;
    expected_version: number;
    manifest_hash: string;
  } | null>(null);
  const command = useServiceCommand(openingRequest, 'opening stock'),
    frozen = useRef<Parameters<typeof command.execute>[0] | null>(null);
  const guard = useAccessDraft(
    lines !== null || entryDirty || draftDirty || !!reason || command.uncertain,
    command.pending,
  );
  const current = control.data,
    ready = readiness.data,
    saved = manifest.data;
  const protectedRead = [
    readiness.failure,
    control.failure,
    manifest.failure,
  ].some((failure) => failure?.status === 403);
  const allLines = protectedRead ? [] : (lines ?? saved?.lines ?? []),
    activeMode = saved && lines === null ? saved.opening_mode : mode;
  useEffect(()=>{
    const lastPage=Math.max(0,Math.ceil(allLines.length/pageSize)-1)*pageSize;
    setOffset(current=>Math.min(current,lastPage));
  },[allLines.length,pageSize]);
  const cutoverBlocked = !!ready?.blockers.some((code) =>
    ['EXECUTION_UNCONFIRMED', 'BOOKS_BEGIN_PERIOD_NOT_OPEN', 'LATER_BOOKS_CLOSED'].includes(code),
  );
  const editable =
    access.manage &&
    !!ready &&
    (ready.can_start ||
      (current?.status === 'OPEN' && !current.applied_cohorts)) &&
    !cutoverBlocked &&
    !command.pending &&
    !command.uncertain &&
    !manifest.loading &&
    !control.loading &&
    !manifest.failure &&
    !control.failure &&
    (!id || !!saved);
  function refresh() {
    readiness.refresh();
    control.refresh();
    manifest.refresh();
    preview.refresh();
    reconciliation.refresh();
  }
  const onDirty = useCallback((dirty: boolean) => setEntryDirty(dirty), []);
  async function execute(request: Parameters<typeof command.execute>[0]) {
    frozen.current = request;
    const result = await command.execute<Control>(
      request,
      verifyControl(company),
    );
    if (result) {
      editVersion.current = null;
      setLines(null);
      setReason('');
      setMessage(
        'Company opening updated. Review the refreshed state before continuing.',
      );
      refresh();
    }
  }
  async function act() {
    if (!ready || !confirm) return;
    const action = confirm;
    setConfirm(null);
    setMessage('');
    const auditReason = reason.trim();
    if (
      auditReason.length < 3 ||
      auditReason.length > 500 ||
      /[\x00-\x1f\x7f]/.test(auditReason)
    ) {
      setMessage('Enter a printable reason between 3 and 500 characters.');
      return;
    }
    if (action === 'zero') {
      await execute({
        method: 'POST',
        path: base + '/confirm-zero',
        body: {
          expected_generation: ready.expected_generation,
          reason: auditReason,
        },
      });
      return;
    }
    const document: Manifest = {
      stock_date: ready.books_begin_date,
      currency: saved?.currency ?? currency,
      opening_mode: activeMode,
      reason: auditReason,
      lines: allLines,
    };
    if (action === 'adopt') {
      await execute({
        method: 'POST',
        path: base + '/adopt',
        body: { ...document, lines: [], adopt_existing: true },
      });
      return;
    }
    if (action === 'save') {
      if (
        lines !== null &&
        // A null baseline means editing began before any worksheet existed.
        // Never turn that registration into replacement after a conflict/reload.
        (current?.id !== editVersion.current?.id ||
          current?.expected_version !== editVersion.current?.expected_version ||
          current?.manifest_hash !== editVersion.current?.manifest_hash)
      ) {
        setMessage(
          'The worksheet changed while you were editing. Discard your local worksheet changes, reload and review the latest declaration.',
        );
        return;
      }
      const issues = allLines
        .map((line) => validateAllocation(line, activeMode))
        .filter(Boolean);
      const serials = allLines.flatMap((line) => line.unit_ids ?? []),
        keys = allLines.map((line) => line.opening?.source_key);
      if (
        !allLines.length ||
        allLines.length > 1000 ||
        issues.length ||
        new Set(keys).size !== keys.length ||
        new Set(serials).size !== serials.length
      ) {
        setMessage(
          issues[0] ??
            'Add 1–1000 unique allocations without duplicate serials or source references.',
        );
        return;
      }
      await execute({
        method: 'POST',
        path: current ? `${base}/${current.id}/replace` : base,
        body: current
          ? {
              expected_version:
                editVersion.current?.expected_version ??
                current.expected_version,
              manifest_hash:
                editVersion.current?.manifest_hash ?? current.manifest_hash,
              reason: auditReason,
              manifest: document,
            }
          : document,
      });
      return;
    }
    if (!current) return;
    await execute({
      method: 'POST',
      path: `${base}/${current.id}/${action}`,
      body: {
        expected_version: current.expected_version,
        manifest_hash: current.manifest_hash,
        reason: auditReason,
      },
    });
  }
  const columns: Column<Allocation>[] = [
    {
      key: 'item_id',
      header: 'Product',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={'/inventory/stock?item_id=' + row.item_id}
          onClick={guard.leave}
        >
          View stock · {row.item_id.slice(-8)}
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
          onClick={guard.leave}
        >
          View warehouse · {row.warehouse_id.slice(-8)}
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
      key: 'received_value',
      header: 'Carrying value',
      type: 'custom',
      render: (row) =>
        row.received_value == null
          ? 'Protected'
          : format.money(row.received_value, { display: 'none' }),
    },
    {
      key: 'opening',
      header: 'Receipt history',
      type: 'custom',
      render: (row) =>
        row.opening?.history_known && row.opening.received_on
          ? format.date(row.opening.received_on)
          : 'Unknown',
    },
    {
      key: 'line_id',
      header: 'Action',
      type: 'custom',
      render: (row) =>
        editable ? (
          <Button
            variant="ghost"
            onClick={() => {
              if (lines === null) editVersion.current = current;
              setMode(activeMode);
              setLines(allLines.filter((line) => line.line_id !== row.line_id));
            }}
          >
            Remove allocation
          </Button>
        ) : (
          'Review only'
        ),
    },
  ];
  return (
    <div className="janso-page">
      <PageNavigation
        back={{
          href: initialItemId
            ? '/inventory/stock?item_id=' + initialItemId
            : '/inventory/stock',
          label: 'stock',
        }}
        onNavigate={guard.leave}
        breadcrumbs={[
          { label: 'Masters', href: '/masters' },
          { label: 'Stock', href: '/inventory/stock' },
          { label: 'Product opening stock' },
        ]}
      />
      <PageHeader
        title="Product opening stock"
        lede="Prepare one company worksheet at books begin, create opening drafts, then reconcile and finalize the company opening."
      />
      <AccountingFailure
        failure={
          readiness.failure ??
          control.failure ??
          manifest.failure ??
          command.failure
        }
        retry={refresh}
      />
      {(readiness.loading || control.loading || manifest.loading) && (
        <Skeleton />
      )}
      {message && (
        <Notice>
          <span>{message}</span>
        </Notice>
      )}
      {command.uncertain && (
        <Notice tone="warning">
          The last update is unconfirmed. Editing is locked to preserve the
          exact request.
          <Button
            onClick={() => frozen.current && void execute(frozen.current)}
            disabled={command.pending}
          >
            Retry the same update
          </Button>
        </Notice>
      )}
      {command.failure && !command.uncertain && (
        <Button
          variant="ghost"
          onClick={() => {
            command.clear();
            refresh();
          }}
        >
          Reload and review latest state
        </Button>
      )}
      {ready && (
        <>
          <Card>
            <CardBody>
              <ReviewList
                items={[
                  {
                    label: 'Books begin',
                    value: format.date(ready.books_begin_date),
                  },
                  { label: 'Currency', value: current?.currency ?? currency },
                  {
                    label: 'Company opening',
                    value: ready.status.replaceAll('_', ' ').toLowerCase(),
                  },
                  {
                    label: 'Applied allocations',
                    value: current
                      ? `${current.applied_cohorts} / ${current.expected_cohorts}`
                      : 'Not declared',
                  },
                ]}
              />
              <div className="janso-flow">
                {ready.blockers.map((code) => (
                  <Notice
                    key={code}
                    tone={
                      code === 'STOCK_POSTING_NOT_ENABLED' ? 'warning' : 'info'
                    }
                  >
                    {blockers[code]?.label ??
                      code.replaceAll('_', ' ').toLowerCase()}
                    {blockers[code]?.href && (
                      <a
                        className="janso-link"
                        href={
                          code === 'BOOKS_BEGIN_PERIOD_NOT_OPEN' ||
                          code === 'LATER_BOOKS_CLOSED'
                            ? '/companies/' + company + '/years'
                            : blockers[code]!.href
                        }
                        onClick={guard.leave}
                      >
                        {' '}
                        Review setup
                      </a>
                    )}
                  </Notice>
                ))}
              </div>
            </CardBody>
          </Card>
          <nav className="janso-tabs" aria-label="Opening stock workspace">
            {(['worksheet', 'drafts', 'completion', 'history'] as const).map(
              (value) => (
                <button
                  key={value}
                  type="button"
                  className="janso-tabs__tab"
                  aria-current={tab === value ? 'page' : undefined}
                  disabled={
                    command.pending ||
                    ((entryDirty || draftDirty) && value !== tab) ||
                    (lines !== null && value !== 'worksheet')
                  }
                  onClick={() => setTab(value)}
                >
                  {
                    {
                      worksheet: 'Worksheet',
                      drafts: 'Drafts and imports',
                      completion: 'Reconcile and complete',
                      history: 'History and corrections',
                    }[value]
                  }
                </button>
              ),
            )}
          </nav>
          {tab === 'worksheet' && (
            <div className="janso-flow">
              {!access.manage && (
                <Notice>
                  Your access allows review. A financial controller with stock
                  configuration and period-post access manages the company
                  worksheet.
                </Notice>
              )}
              {editable && (
                <>
                  <Select
                    label="Accounting treatment"
                    value={activeMode}
                    disabled={entryDirty||!!allLines.length}
                    onChange={(value) => {
                      if(entryDirty||allLines.length)return;
                      if (lines === null)
                        editVersion.current = current;
                      setLines([...allLines]);
                      setMode(value as Manifest['opening_mode']);
                    }}
                    options={[
                      {
                        value: 'COMBINED',
                        label: 'Create inventory and opening-offset entries',
                      },
                      {
                        value: 'LINKED_GL',
                        label: 'Use existing posted inventory opening entries',
                      },
                    ]}
                  />
                  <Notice>
                    {activeMode === 'COMBINED'
                      ? 'Posting will debit configured inventory accounts and credit the opening-offset account.'
                      : 'Posting will consume matching unclaimed opening-journal coverage without creating additional GL entries.'}
                  </Notice>
                  <OpeningStockEntry
                    key={company + ':' + activeMode}
                    company={company}
                    date={ready.books_begin_date}
                    currency={saved?.currency ?? currency}
                    mode={activeMode}
                    initialItemId={initialItemId}
                    disabled={!editable}
                    onDirty={onDirty}
                    onAdd={(line) => {
                      if (lines === null)
                        editVersion.current = current;
                      setMode(activeMode);
                      setLines([...allLines, line]);
                    }}
                  />
                </>
              )}
              <Card>
                <DataTable
                  caption="Company opening worksheet"
                  columns={columns}
                  rows={allLines.slice(offset, offset + pageSize)}
                  rowId={(row) => row.line_id}
                  rowLabel={(row) =>
                    row.opening?.source_key ?? 'Opening allocation'
                  }
                  loading={manifest.loading}
                  emptyTitle="No declared opening allocations"
                  emptyBody="Add products and their warehouse quantities and carrying values. Saving this worksheet does not post stock."
                />
                <Pager
                  count={Math.min(
                    pageSize,
                    Math.max(0, allLines.length - offset),
                  )}
                  limit={pageSize}
                  busy={command.pending}
                  hasPrevious={offset > 0}
                  hasNext={offset + pageSize < allLines.length}
                  onPrevious={() => setOffset(Math.max(0, offset - pageSize))}
                  onNext={() => setOffset(offset + pageSize)}
                  onLimitChange={(limit) => {
                    setPageSize(limit);
                    setOffset(0);
                  }}
                  noun="allocation"
                />
                <CardBody>
                  <ReviewList
                    items={[
                      { label: 'Allocations', value: String(allLines.length) },
                      {
                        label: 'Declared carrying value',
                        value: protectedRead
                          ? 'Protected'
                          : !saved && lines === null
                            ? 'Not declared'
                            : allLines.every(
                                  (line) => line.received_value != null,
                                )
                              ? format.money(
                                  sum(
                                    allLines.map(
                                      (line) => line.received_value!,
                                    ),
                                  ),
                                  { display: 'none' },
                                ) +
                                ' ' +
                                (saved?.currency ?? currency)
                              : 'Protected',
                      },
                    ]}
                  />
                  {editable && (
                    <>
                      <TextField
                        label="Reason for worksheet change"
                        value={reason}
                        maxLength={500}
                        onChange={(event) => setReason(event.target.value)}
                        required
                      />
                      <div className="janso-form-actions">
                        <Button
                          onClick={() => setConfirm('save')}
                          disabled={
                            entryDirty ||
                            !allLines.length ||
                            reason.trim().length < 3
                          }
                          loading={command.pending}
                        >
                          Review and save worksheet
                        </Button>
                        {lines !== null && (
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setConfirm(null);
                              editVersion.current = null;
                              setLines(null);
                            }}
                          >
                            Discard worksheet changes
                          </Button>
                        )}
                      </div>
                    </>
                  )}
                </CardBody>
              </Card>
            </div>
          )}
          {tab === 'drafts' &&
            (access.importRead ? (
              <OpeningStockImports
                company={company}
                access={access}
                control={current}
                manifest={saved}
                onChanged={() => {
                  control.refresh();
                  preview.refresh();
                  reconciliation.refresh();
                }}
                onDirty={setDraftDirty}
              />
            ) : (
              <Notice>
                Opening import-read and voucher-read access are required to
                review draft preparation.
              </Notice>
            ))}
          {tab === 'completion' && (
            <Card>
              <CardBody>
                <div className="janso-flow">
                  <h2>Reconcile company opening</h2>
                  <AccountingFailure
                    failure={reconciliation.failure ?? preview.failure}
                    retry={() => {
                      reconciliation.refresh();
                      preview.refresh();
                    }}
                  />
                  {current && (
                    <ReviewList
                      stacked
                      items={[
                        {
                          label: 'Declared value',
                          value:
                            format.money(current.expected_value, {
                              display: 'none',
                            }) +
                            ' ' +
                            current.currency,
                        },
                        {
                          label: 'Applied value',
                          value:
                            format.money(current.applied_value, {
                              display: 'none',
                            }) +
                            ' ' +
                            current.currency,
                        },
                        {
                          label: 'Missing allocations',
                          value: String(current.missing_source_keys.length),
                        },
                        {
                          label: 'Legacy history adopted',
                          value: current.legacy_adopted ? 'Yes' : 'No',
                        },
                      ]}
                    />
                  )}
                  {current?.missing_source_keys.length ? (
                    <details>
                      <summary>Missing allocation references</summary>
                      <ul>
                        {current.missing_source_keys.map((key) => (
                          <li key={key}>{key}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                  {preview.data && (
                    <>
                      <h3>Accounting preview</h3>
                      <ReviewList
                        items={[
                          {
                            label: 'Remaining stock value',
                            value: format.money(preview.data.remaining_value, {
                              display: 'none',
                            }),
                          },
                          {
                            label: 'Additional GL value',
                            value: format.money(
                              preview.data.additional_gl_value,
                              { display: 'none' },
                            ),
                          },
                        ]}
                      />
                      <ul>
                        {preview.data.entries.map((entry, index) => (
                          <li key={index}>
                            {entry.side}:{' '}
                            {format.money(entry.amount, { display: 'none' })} ·{' '}
                            <a
                              className="janso-link"
                              href={'/masters/accounts/' + entry.account_id}
                            >
                              View account
                            </a>
                          </li>
                        ))}
                      </ul>
                      <p>
                        {preview.data.linked_claims.length} linked journal
                        claims. Preview is informational until native posting
                        confirms.
                      </p>
                    </>
                  )}
                  <TextField
                    label="Completion or correction reason"
                    value={reason}
                    maxLength={500}
                    onChange={(event) => setReason(event.target.value)}
                    disabled={command.pending || command.uncertain}
                  />
                  <div className="janso-form-actions">
                    <Button
                      variant="ghost"
                      onClick={refresh}
                      disabled={command.pending}
                    >
                      Refresh reconciliation
                    </Button>
                    {access.zero && ready.can_confirm_zero && (
                      <Button
                        onClick={() => setConfirm('zero')}
                        disabled={
                          reason.trim().length < 3 ||
                          command.pending ||
                          command.uncertain
                        }
                      >
                        Confirm zero stock opening
                      </Button>
                    )}
                    {access.manage && ready.status === 'LEGACY_ACTIVITY' && (
                      <Button
                        onClick={() => setConfirm('adopt')}
                        disabled={
                          cutoverBlocked ||
                          reason.trim().length < 3 ||
                          command.pending ||
                          command.uncertain
                        }
                      >
                        Review and adopt existing stock history
                      </Button>
                    )}
                    {access.manage && current?.status === 'OPEN' && (
                      <Button
                        onClick={() => setConfirm('finalize')}
                        disabled={
                          reason.trim().length < 3 ||
                          !reconciliation.data ||
                          reconciliation.loading ||
                          !!reconciliation.failure ||
                          !!reconciliation.data.blockers.length ||
                          command.pending ||
                          command.uncertain
                        }
                      >
                        Finalize company opening
                      </Button>
                    )}
                    {access.manage &&
                      current?.status === 'FINALIZED' &&
                      !current.legacy_adopted && (
                        <Button
                          variant="ghost"
                          onClick={() => setConfirm('reopen')}
                          disabled={
                            reason.trim().length < 3 ||
                            command.pending ||
                            command.uncertain
                          }
                        >
                          Request reviewed reopening
                        </Button>
                      )}
                  </div>
                  <Notice>
                    Zero stock confirmation declares no physical opening stock.
                    It does not initialize or finalize financial opening
                    balances. Legacy adoption acknowledges reconciled existing
                    history and does not clear quantities or value.
                  </Notice>
                </div>
              </CardBody>
            </Card>
          )}
          {tab === 'history' &&
            (current ? (
              <OpeningStockHistory
                company={company}
                control={current}
                access={access}
                initialItemId={initialItemId}
              />
            ) : (
              <Notice>
                History becomes available after the company opening is declared.
              </Notice>
            ))}
        </>
      )}
      <ConfirmDialog
        open={!!confirm}
        title={
          {
            save: 'Save company opening worksheet?',
            zero: 'Confirm no opening stock?',
            adopt: 'Adopt reconciled existing stock history?',
            finalize: 'Finalize the entire company opening?',
            reopen: 'Reopen company opening for reviewed correction?',
          }[confirm ?? 'save']
        }
        confirmLabel="Confirm"
        busy={command.pending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => void act()}
      >
        {confirm === 'save'
          ? `${allLines.length} allocations will become the company declaration. This saves evidence only; no stock or accounting is posted.`
          : confirm === 'zero'
            ? 'Confirm that this company has no physical opening stock or stock opening GL claims. The server rechecks history and the accounting generation.'
            : confirm === 'adopt'
              ? 'Confirm you have reviewed and reconciled all existing stock history. This does not replace existing balances with an empty worksheet.'
              : confirm === 'finalize'
                ? 'This completes the opening for every product and warehouse in the company. All declared allocations, physical quantities and GL coverage must reconcile.'
                : 'The server rechecks period locks, stock dependencies and existing claims. Posted balances remain immutable.'}
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}

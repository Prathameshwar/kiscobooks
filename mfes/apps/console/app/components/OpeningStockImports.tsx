'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  DataTable,
  FileUpload,
  Notice,
  Pager,
  ReviewList,
  SearchSelect,
  TextField,
  type Column,
} from '@janso/ui';
import {
  importBase,
  openingImportRequest,
  openingDownload,
  verifyJob,
  type OpeningAccess,
  type ImportJob,
  type ImportStage,
  type Control,
  type Manifest,
} from '../lib/opening-stock';
import { openingDraftDocument } from '../lib/opening-stock-drafts';
import {
  useServiceCommand,
  useServiceList,
  useServiceRead,
} from '../lib/service-resource';
import { lookup } from '../lib/voucher-fields';
import { trackingId } from '../lib/stock-tracking-resources';
import { useAccessDraft } from './AccessCommon';
import { AccountingFailure } from './AccountingConfigurationCommon';

export function OpeningStockImports({
  company,
  access,
  control,
  manifest,
  onChanged,
  onDirty,
}: {
  company: string;
  access: OpeningAccess;
  control: Control | null;
  manifest: Manifest | null;
  onChanged: () => void;
  onDirty?: (dirty: boolean) => void;
}) {
  const base = importBase(company),
    [selected, setSelected] = useState<string | null>(null),
    [job, setJob] = useState<ImportJob | null>(null),
    [source, setSource] = useState(''),
    [file, setFile] = useState<File | null>(null),
    [type, setType] = useState<string | null>(null),
    [error, setError] = useState(''),
    [preparing, setPreparing] = useState(false),
    [progress, setProgress] = useState(''),
    [confirm, setConfirm] = useState<'commit' | 'cancel' | null>(null);
  const command = useServiceCommand(
      openingImportRequest,
      'opening draft service',
    ),
    frozen = useRef<Parameters<typeof command.execute>[0] | null>(null);
  const list = useServiceList<{
    id: string;
    source_key: string;
    state: string;
    row_version: number;
  }>(
    base,
    '',
    openingImportRequest,
    (row) => {
      if (!trackingId.test(row.id))
        throw { status: 502, message: 'Import history could not be verified.' };
    },
    access.importRead,
  );
  const template = useServiceRead<{
    marker: string;
    version: number;
    required_columns: string[];
    optional_columns: string[];
    reference_policy: string;
    effect: string;
  }>(
    access.draft ? base + '/template' : undefined,
    openingImportRequest,
    (value) => {
      if (
        value.marker !== '_stock_opening_schema_version' ||
        value.version !== 1 ||
        !Array.isArray(value.required_columns) ||
        !Array.isArray(value.optional_columns) ||
        [...value.required_columns, ...value.optional_columns].some(
          (column) => !/^[a-z_]+$/.test(column),
        )
      )
        throw {
          status: 502,
          message: 'The opening template version could not be verified.',
        };
    },
  );
  const guard = useAccessDraft(
    !!file || command.uncertain,
    preparing || command.pending,
  );
  useEffect(() => {
    onDirty?.(!!file || command.uncertain || preparing || command.pending);
    return () => onDirty?.(false);
  }, [file, command.uncertain, preparing, command.pending, onDirty]);
  const locked = command.pending || command.uncertain || preparing;
  async function run(request: Parameters<typeof command.execute>[0]) {
    frozen.current = request;
    const result = await command.execute<ImportJob>(
      request,
      verifyJob(company),
    );
    if (result) {
      setSelected(result.id);
      setJob(result);
      setFile(null);
      list.first();
      onChanged();
    }
  }
  async function refresh(id = selected) {
    if (!id) return;
    setError('');
    try {
      const result = await openingImportRequest<ImportJob>({
        path: base + '/' + id,
      });
      verifyJob(company)(result);
      setSelected(id);
      setJob(result);
    } catch (reason) {
      setJob(null);
      setError(
        reason && typeof reason === 'object' && 'message' in reason
          ? String(reason.message)
          : 'Unable to load draft job.',
      );
    }
  }
  async function stage(manual: boolean) {
    if (preparing || locked) return;
    setPreparing(true);
    setError('');
    try {
      let body: ImportStage;
      if (manual) {
        if (!control || !manifest || !type)
          throw new Error(
            'Save the company worksheet and select an opening-stock voucher type first.',
          );
        const document = await openingDraftDocument(
          company,
          control,
          manifest,
          type,
          (done, total) =>
            setProgress(
              `Verified ${done} of ${total} products for native draft preparation.`,
            ),
        );
        body = {
          source_key: `worksheet-${control.id}-${control.expected_version}`,
          format: 'JSON',
          document,
        };
      } else {
        if (!file || !source.trim())
          throw new Error(
            'Choose an import file and enter a stable import reference.',
          );
        const extension = file.name.split('.').at(-1)?.toUpperCase();
        if (
          !['CSV', 'TSV', 'XLSX', 'JSON'].includes(extension ?? '') ||
          file.size > 2 * 1024 * 1024
        )
          throw new Error('Choose CSV, TSV, XLSX or JSON up to 2 MiB.');
        if (extension === 'JSON')
          body = {
            source_key: source.trim(),
            format: 'JSON',
            document: JSON.parse(await file.text()) as ImportStage['document'],
          };
        else {
          const bytes = new Uint8Array(await file.arrayBuffer());
          let binary = '';
          for (let i = 0; i < bytes.length; i += 8192)
            binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
          body = {
            source_key: source.trim(),
            format: extension as 'CSV' | 'TSV' | 'XLSX',
            content_base64: btoa(binary),
          };
        }
      }
      await run({ method: 'POST', path: base, body });
    } catch (reason) {
      setError(
        reason && typeof reason === 'object' && 'message' in reason
          ? String(reason.message)
          : 'Unable to prepare the import. Review the file and references.',
      );
    } finally {
      setPreparing(false);
      setProgress('');
    }
  }
  async function action(action: 'validate' | 'commit' | 'cancel') {
    if (!job) return;
    setConfirm(null);
    await run({
      method: 'POST',
      path: `${base}/${job.id}/${action}`,
      body: {
        expected_version: job.row_version,
        ...(action === 'commit' ? { review_hash: job.review_hash } : {}),
      },
    });
  }
  const columns: Column<{
    id: string;
    source_key: string;
    state: string;
    row_version: number;
  }>[] = [
    {
      key: 'source_key',
      header: 'Reference',
      type: 'custom',
      render: (row) => (
        <Button
          variant="ghost"
          disabled={locked}
          onClick={() => void refresh(row.id)}
        >
          {row.source_key}
        </Button>
      ),
    },
    {
      key: 'state',
      header: 'Draft preparation status',
      type: 'custom',
      render: (row) => row.state.replaceAll('_', ' ').toLowerCase(),
    },
  ];
  return (
    <div className="janso-flow">
      <Notice>
        Imports and worksheet preparation create native voucher drafts only.
        Approval and stock posting happen through each voucher’s normal
        workflow. No quantity or value is posted here.
      </Notice>
      <AccountingFailure
        failure={command.failure ?? list.failure ?? template.failure}
        retry={() => {
          list.first();
          template.refresh();
        }}
      />
      {error && (
        <Notice tone="danger">
          <span role="alert">{error}</span>
        </Notice>
      )}
      {command.uncertain && (
        <Notice tone="warning">
          The result is unconfirmed. Keep this request unchanged.
          <Button
            onClick={() => frozen.current && void run(frozen.current)}
            disabled={command.pending}
          >
            Retry the same request
          </Button>
        </Notice>
      )}
      {!command.uncertain && command.failure && (
        <Button
          variant="ghost"
          onClick={() => {
            command.clear();
            void refresh();
          }}
        >
          Reload and review
        </Button>
      )}
      {access.draft && (
        <Card>
          <CardBody>
            <div className="janso-flow">
              <h2>Prepare opening drafts</h2>
              {progress && <p role="status">{progress}</p>}
              <SearchSelect
                label="Opening-stock voucher type"
                value={type}
                loadOptions={lookup(company, 'voucher_types')}
                scopeKey={company}
                minQueryLength={0}
                onChange={setType}
                disabled={locked}
                hint="Its published profile must be Opening stock and match the worksheet accounting treatment."
              />
              <Button
                onClick={() => void stage(true)}
                disabled={
                  locked ||
                  !control ||
                  control.status !== 'OPEN' ||
                  !manifest?.lines?.length ||
                  !type ||
                  !!control.applied_cohorts
                }
                loading={preparing}
              >
                Prepare saved worksheet
              </Button>
              <h3>Or upload opening drafts</h3>
              <TextField
                label="Import reference"
                value={source}
                maxLength={100}
                onChange={(event) => setSource(event.target.value)}
                disabled={locked}
                hint="Keep this reference for retries. Changed content needs a new reference."
              />
              <FileUpload
                label="Opening-stock file"
                disabled={locked}
                accept=".csv,.tsv,.xlsx,.json"
                maxSizeBytes={2 * 1024 * 1024}
                maxFiles={1}
                items={
                  file
                    ? [
                        {
                          id: 'opening-file',
                          name: file.name,
                          size: file.size,
                          status: 'pending',
                        },
                      ]
                    : []
                }
                onSelect={(files) => {
                  if (!locked) setFile(files[0] ?? null);
                }}
                onRemove={() => {
                  if (!locked) setFile(null);
                }}
              />
              <Button
                onClick={() => void stage(false)}
                disabled={locked || !file || !source.trim()}
              >
                Stage and inspect file
              </Button>
              {template.data && (
                <details>
                  <summary>Template and reference requirements</summary>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      const definition = template.data!;
                      const csv =
                        definition.marker +
                        ',1\r\n' +
                        [
                          ...definition.required_columns,
                          ...definition.optional_columns,
                        ].join(',') +
                        '\r\n';
                      const url = URL.createObjectURL(
                        new Blob([csv], { type: 'text/csv;charset=utf-8' }),
                      );
                      const anchor = document.createElement('a');
                      anchor.href = url;
                      anchor.download = 'opening-stock-template.csv';
                      anchor.click();
                      setTimeout(() => URL.revokeObjectURL(url), 1000);
                    }}
                  >
                    Download CSV template
                  </Button>
                  <p>{template.data.reference_policy}</p>
                  <p>{template.data.effect}</p>
                  <p>
                    Use the owner’s versioned schema, native IDs and exact
                    decimal text. Save a matching company worksheet before
                    preparing its drafts.
                  </p>
                  <pre className="janso-preview__text">
                    {JSON.stringify(template.data, null, 2)}
                  </pre>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      const url = URL.createObjectURL(
                        new Blob([JSON.stringify(template.data, null, 2)], {
                          type: 'application/json',
                        }),
                      );
                      const link = document.createElement('a');
                      link.href = url;
                      link.download = 'opening-stock-template.json';
                      link.click();
                      setTimeout(() => URL.revokeObjectURL(url), 1000);
                    }}
                  >
                    Download template specification
                  </Button>
                </details>
              )}
            </div>
          </CardBody>
        </Card>
      )}
      {job && !list.failure && (
        <Card>
          <CardBody>
            <div className="janso-flow">
              <h2>Draft preparation result</h2>
              <ReviewList
                stacked
                items={[
                  { label: 'Reference', value: job.source_key },
                  {
                    label: 'Status',
                    value: job.state.replaceAll('_', ' ').toLowerCase(),
                  },
                  {
                    label: 'Validated chunks',
                    value: `${job.validated_chunks} / ${job.chunk_count}`,
                  },
                  {
                    label: 'Draft chunks created',
                    value: `${job.created_chunks} / ${job.chunk_count}`,
                  },
                ]}
              />
              {job.errors.map((issue, index) => (
                <Notice key={index} tone="danger">
                  Chunk {String(issue.chunk ?? index + 1)}:{' '}
                  {String(issue.message ?? issue.code ?? 'Review this chunk.')}
                </Notice>
              ))}
              {job.effects.map((effect, index) => (
                <p key={index}>
                  Chunk {String(effect.chunk ?? index + 1)}:{' '}
                  {trackingId.test(String(effect.voucher_id ?? '')) ? (
                    <a
                      className="janso-link"
                      href={'/vouchers/' + effect.voucher_id}
                    >
                      Open voucher ·{' '}
                      {String(effect.voucher_status ?? 'draft created')}
                    </a>
                  ) : (
                    'Confirmation pending'
                  )}
                </p>
              ))}
              <div className="janso-form-actions">
                <Button
                  variant="ghost"
                  onClick={() => void refresh()}
                  disabled={locked}
                >
                  Refresh job
                </Button>
                {access.draft &&
                  ['STAGED', 'VALIDATING', 'BLOCKED', 'READY'].includes(
                    job.state,
                  ) && (
                    <Button
                      onClick={() => void action('validate')}
                      disabled={locked}
                    >
                      {job.state === 'READY'
                        ? 'Revalidate draft chunks'
                        : 'Validate next chunks'}
                    </Button>
                  )}
                {access.commit &&
                  ['READY', 'COMMITTING'].includes(job.state) && (
                    <Button
                      onClick={() => setConfirm('commit')}
                      disabled={locked || !job.review_hash}
                    >
                      {job.state === 'COMMITTING'
                        ? 'Continue creating drafts'
                        : 'Review and create drafts'}
                    </Button>
                  )}
                {access.draft &&
                  !['CANCELLED', 'DRAFTS_CREATED'].includes(job.state) && (
                    <Button
                      variant="ghost"
                      onClick={() => setConfirm('cancel')}
                      disabled={locked}
                    >
                      Cancel remaining preparation
                    </Button>
                  )}
                <Button
                  variant="ghost"
                  onClick={() =>
                    void openingDownload(
                      'vouchers',
                      `${base}/${job.id}/report-ticket`,
                      company,
                    ).catch((reason) => setError(String(reason.message)))
                  }
                  disabled={locked}
                >
                  Download result report
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      )}
      <Card>
        <DataTable
          caption="Opening draft preparation history"
          columns={columns}
          rows={list.data?.items ?? []}
          rowId={(row) => row.id}
          rowLabel={(row) => row.source_key}
          loading={list.loading}
          emptyTitle="No opening draft jobs"
          emptyBody="Prepared jobs appear here so you can resume after leaving this page."
        />
        <Pager
          count={list.data?.items.length ?? 0}
          limit={list.limit}
          busy={list.loading}
          hasPrevious={list.hasPrevious}
          hasNext={!!list.data?.page.has_more}
          onPrevious={list.previous}
          onNext={list.next}
          onLimitChange={list.setLimit}
          noun="job"
        />
      </Card>
      <ConfirmDialog
        open={!!confirm}
        title={
          confirm === 'commit'
            ? 'Create native opening drafts?'
            : 'Cancel remaining draft preparation?'
        }
        confirmLabel={
          confirm === 'commit' ? 'Create drafts' : 'Cancel remaining'
        }
        busy={command.pending}
        onCancel={() => setConfirm(null)}
        onConfirm={() => confirm && void action(confirm)}
      >
        {confirm === 'commit'
          ? 'The reviewed chunks will create voucher drafts. This does not approve vouchers or post stock. Each click advances at most two chunks; remaining work stays resumable.'
          : 'Already created vouchers remain available and must be cancelled through their native workflow.'}
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}

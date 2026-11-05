'use client';
import { useEffect, useState } from 'react';
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Disclosure,
  EmptyState,
  Notice,
  Pager,
  Select,
  Skeleton,
  useFormatters,
  type Column,
} from '@janso/ui';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import {
  productImportProfile,
  type MasterImportProfile,
} from '../lib/master-import-profiles';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import {
  importBase,
  importId,
  importStateLabel,
  importStateTone,
  useImportList,
  type ImportArtifact,
  type ImportAttempt,
  type ImportIssue,
  type ImportJob,
  type ImportRecord,
  type ImportRevision,
} from '../lib/product-import';

export function ImportPaging({
  list,
  noun,
}: {
  list: ReturnType<typeof useImportList<{ id: string }>>;
  noun: string;
}) {
  return list.data && !list.failure ? (
    <Pager
      count={list.data.items.length}
      limit={list.limit}
      noun={noun}
      hasPrevious={list.hasPrevious}
      hasNext={list.data.page.has_more}
      onPrevious={list.previous}
      onNext={list.next}
      busy={list.loading}
    />
  ) : null;
}
export function ProductImportResults({
  company,
  job,
  here,
  download,
  downloading,
  onLeave,
  profile = productImportProfile,
}: {
  company: string;
  job: ImportJob;
  here: string;
  download: (
    kind: 'RESULT' | 'SOURCE',
    artifact?: ImportArtifact,
    attempt?: string,
    revision?: number,
  ) => void;
  downloading: boolean;
  onLeave: React.MouseEventHandler<HTMLAnchorElement>;
  profile?: MasterImportProfile;
}) {
  const path = importBase(company) + '/import-jobs/' + job.id,
    format = useFormatters(),
    expired = Date.parse(job.expires_at) <= Date.now();
  const records = useImportList<ImportRecord>(
      profile.readyProducts || expired ? undefined : path + '/records',
      profile.request,
    ),
    attempts = useImportList<ImportAttempt>(
      path + '/history/attempts',
      profile.request,
    );
  const artifacts = useImportList<ImportArtifact>(
      path + '/history/artifacts',
      profile.request,
    ),
    revisions = useImportList<ImportRevision>(
      path + '/history/revisions',
      profile.request,
    );
  const [selected, setSelected] = useState('');
  useEffect(() => {
    setSelected(attempts.data?.items.at(-1)?.id ?? '');
  }, [attempts.data]);
  const messages = useImportList<ImportIssue>(
    selected && !expired
      ? path + '/attempts/' + selected + '/issues'
      : undefined,
    profile.request,
  );
  // A revision is bounded to 200 commands. One bounded lookup resolves message
  // locations even when its record is outside the currently displayed row page.
  const locations = useServiceRead<ServicePage<ImportRecord>>(
    !expired &&
      (profile.readyProducts
        ? !!messages.data?.items.length
        : records.data?.page.has_more)
      ? path + '/records?limit=200'
      : undefined,
    profile.request,
  );
  const rowLabels = new Map(
    (locations.data?.items ?? records.data?.items)?.map((row) => [
      row.id,
      row.source_file +
        ' · ' +
        row.source_sheet +
        ' row ' +
        row.source_row +
        ' · ' +
        row.logical_key,
    ]),
  );
  const recordColumns: Column<ImportRecord>[] = [
    { key: 'source_file', header: 'File', type: 'text' },
    { key: 'source_sheet', header: 'Sheet', type: 'text' },
    {
      key: 'source_row',
      header: 'Row',
      type: 'custom',
      render: (row) => String(row.source_row),
    },
    { key: 'logical_key', header: 'Row key', type: 'code' },
    {
      key: 'status',
      header: 'Result',
      type: 'custom',
      render: (row) => (
        <Badge tone={importStateTone(row.status ?? 'STAGED')}>
          {importStateLabel(row.status ?? 'STAGED')}
        </Badge>
      ),
    },
    {
      key: 'business_id',
      header: profile.definition === 'products' ? 'Product' : 'Record',
      type: 'custom',
      render: (row) => {
        const href =
          row.status === 'APPLIED' &&
          row.business_id &&
          importId.test(row.business_id)
            ? profile.destination(row.resource, row.business_id, here)
            : null;
        return href ? (
          <a className="janso-link" href={href} onClick={onLeave}>
            {profile.definition === 'products' ? 'Open product' : 'Open record'}
          </a>
        ) : (
          '—'
        );
      },
    },
  ];
  const messageColumns: Column<ImportIssue>[] = [
    {
      key: 'record_id',
      header: 'Source row',
      type: 'custom',
      render: (row) =>
        rowLabels.get(row.record_id) ??
        'Row reference ' + row.record_id.slice(-8),
    },
    {
      key: 'field',
      header: 'Field',
      type: 'custom',
      render: (row) => row.field || 'Whole row',
    },
    { key: 'message', header: 'Message', type: 'text' },
    { key: 'code', header: 'Code', type: 'code' },
  ];
  return (
    <div className="janso-flow">
      {!profile.readyProducts && (
        <Card>
          <CardHeader title="Row results" />
          <CardBody>
            <div className="janso-flow">
              <ProductCatalogFailure
                failure={records.failure}
                retry={records.first}
              />
              {records.loading ? (
                <div role="status" aria-label="Loading import rows">
                  <Skeleton />
                </div>
              ) : (
                records.data && (
                  <DataTable
                    caption={profile.label + ' import row results'}
                    columns={recordColumns}
                    rows={records.data.items}
                    rowId={(row) => row.id}
                    rowLabel={(row) => row.logical_key}
                  />
                )
              )}
              <ImportPaging list={records} noun="row" />
            </div>
          </CardBody>
        </Card>
      )}
      <Card>
        <CardHeader title="Validation and import history" />
        <CardBody>
          <div className="janso-flow">
            <ProductCatalogFailure
              failure={attempts.failure}
              retry={attempts.first}
            />
            {expired && (
              <Notice>
                Source files and detailed attempt messages have expired.
                Retained product results and attempt history remain available.
              </Notice>
            )}
            {attempts.loading ? (
              <div role="status" aria-label="Loading validation attempts">
                <Skeleton />
              </div>
            ) : attempts.data?.items.length ? (
              <>
                <Select
                  label="Validation or import attempt"
                  value={selected}
                  options={attempts.data.items.map((attempt) => ({
                    value: attempt.id,
                    label:
                      (attempt.phase === 'VALIDATE' ? 'Validation' : 'Import') +
                      ' · ' +
                      attempt.outcome.replaceAll('_', ' ').toLowerCase() +
                      ' · ' +
                      format.dateTime(attempt.created_at),
                  }))}
                  onChange={setSelected}
                />
                {attempts.data.page.has_more && (
                  <Notice>
                    More attempts are available on the next history page.
                  </Notice>
                )}
                <ProductCatalogFailure
                  failure={messages.failure}
                  retry={messages.first}
                />
                <ProductCatalogFailure
                  failure={locations.failure}
                  retry={locations.refresh}
                />
                <p className="janso-fine">
                  Messages refer to the selected attempt. For older file
                  revisions, download that attempt’s results for its complete
                  source locations.
                </p>
                {messages.loading ? (
                  <div role="status" aria-label="Loading import messages">
                    <Skeleton />
                  </div>
                ) : (
                  messages.data &&
                  (messages.data.items.length ? (
                    <DataTable
                      caption="Validation and import messages"
                      columns={messageColumns}
                      rows={messages.data.items}
                      rowId={(row) => row.id}
                      rowLabel={(row) => row.field || row.code}
                    />
                  ) : (
                    <Notice tone="success">
                      No row problems were reported for this attempt.
                    </Notice>
                  ))
                )}
                <ImportPaging list={messages} noun="message" />
                <button
                  type="button"
                  className="janso-btn janso-btn--ghost"
                  disabled={downloading || !selected || expired}
                  onClick={() => download('RESULT', undefined, selected)}
                >
                  Download this attempt’s results
                </button>
              </>
            ) : (
              !attempts.failure && (
                <EmptyState
                  title="Not validated yet"
                  body="Validate the uploaded files to see row-level messages here."
                />
              )
            )}
            <ImportPaging list={attempts} noun="attempt" />
          </div>
        </CardBody>
      </Card>
      <Disclosure summary="Source files and file revisions">
        <div className="janso-flow">
          <ProductCatalogFailure
            failure={artifacts.failure ?? revisions.failure}
            retry={() => {
              artifacts.first();
              revisions.first();
            }}
          />
          {artifacts.loading || revisions.loading ? (
            <div role="status" aria-label="Loading source history">
              <Skeleton />
            </div>
          ) : (
            <>
              <DataTable
                caption="Import source files"
                rows={artifacts.data?.items ?? []}
                rowId={(row) => row.id}
                rowLabel={(row) => row.filename}
                columns={[
                  { key: 'filename', header: 'Source file', type: 'text' },
                  { key: 'format', header: 'Format', type: 'code' },
                  {
                    key: 'expires_at',
                    header: 'Available until',
                    type: 'custom',
                    render: (row) => format.dateTime(row.expires_at),
                  },
                  {
                    key: 'id',
                    header: 'Download',
                    type: 'custom',
                    render: (row) => {
                      const revision = revisions.data?.items.find(
                        (revision) => revision.id === row.revision_id,
                      )?.revision;
                      return (
                        <button
                          type="button"
                          className="janso-btn janso-btn--ghost"
                          title={
                            !revision
                              ? 'Load the corresponding file revision before downloading this source.'
                              : undefined
                          }
                          disabled={
                            downloading ||
                            !revision ||
                            Date.parse(row.expires_at) <= Date.now()
                          }
                          onClick={() =>
                            download('SOURCE', row, undefined, revision)
                          }
                        >
                          Download source
                        </button>
                      );
                    },
                  },
                ]}
              />
              <ImportPaging list={artifacts} noun="source file" />
              <DataTable
                caption="Import file revisions"
                rows={revisions.data?.items ?? []}
                rowId={(row) => row.id}
                rowLabel={(row) => 'Revision ' + row.revision}
                columns={[
                  {
                    key: 'revision',
                    header: 'Revision',
                    type: 'custom',
                    render: (row) => String(row.revision),
                  },
                  {
                    key: 'created_at',
                    header: 'Uploaded',
                    type: 'custom',
                    render: (row) => format.dateTime(row.created_at),
                  },
                ]}
              />
              <ImportPaging list={revisions} noun="revision" />
            </>
          )}
        </div>
      </Disclosure>
    </div>
  );
}

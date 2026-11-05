'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Notice,
  Skeleton,
  type Column,
} from '@janso/ui';
import { useServiceRead } from '../lib/service-resource';
import {
  requestFailure,
  type RequestFailure,
  type ServiceRequest,
} from '../lib/service-call';
import {
  assertImportJob,
  importBase,
  productImportRequest,
  useImportList,
  type ImportJob,
} from '../lib/product-import';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import { ImportPaging } from './ProductImportResults';
import type { components } from '@janso/api-client/catalog';

type Progress = components['schemas']['SimpleImportProgress'];
type Row = components['schemas']['SimpleImportRowResult'];

function verify(value: Progress, id: string) {
  assertImportJob(value?.job, id, 'simple_products');
  if (
    ![value.pending_count, value.failed_count].every(
      (n) => Number.isInteger(n) && n >= 0 && n <= 200,
    ) ||
    typeof value.can_resume !== 'boolean'
  )
    throw { status: 502, message: 'Import progress could not be verified.' };
}

function ProductRows({ path }: { path: string }) {
  const rows = useImportList<Row>(path + '/rows', productImportRequest);
  const columns: Column<Row>[] = [
    {
      key: 'source_file',
      header: 'Source',
      type: 'custom',
      render: (row) => `${row.source_file} · row ${row.source_row}`,
    },
    { key: 'name', header: 'Product', type: 'text' },
    { key: 'code', header: 'Product code', type: 'code' },
    {
      key: 'state',
      header: 'Result',
      type: 'custom',
      render: (row) =>
        row.state === 'APPLIED'
          ? 'Ready'
          : row.state === 'VALID'
            ? 'Valid'
            : row.state === 'PENDING'
              ? 'Processing'
              : row.state.toLowerCase(),
    },
    {
      key: 'opening_posted',
      header: 'Opening stock',
      type: 'custom',
      render: (row) => (row.opening_posted ? 'Posted' : '—'),
    },
    {
      key: 'messages',
      header: 'Messages',
      type: 'custom',
      render: (row) =>
        (row.messages ?? [])
          .map((m) => (m.field ? m.field + ': ' : '') + m.message)
          .join(' · ') || '—',
    },
  ];
  return (
    <>
      <ProductCatalogFailure failure={rows.failure} retry={rows.first} />
      {rows.loading ? (
        <Skeleton />
      ) : (
        rows.data && (
          <DataTable
            caption="Product results"
            columns={columns}
            rows={rows.data.items}
            rowId={(row) => row.id}
            rowLabel={(row) => row.name ?? row.code ?? 'Product'}
          />
        )
      )}
      <ImportPaging list={rows} noun="product" />
    </>
  );
}

export function SimpleProductImportProgress({
  company,
  job,
  canManage,
  autoRun,
  onJob,
  onStarted,
  onPending,
}: {
  company: string;
  job: ImportJob;
  canManage: boolean;
  autoRun: boolean;
  onJob: (job: ImportJob) => void;
  onStarted: () => void;
  onPending: (pending: boolean) => void;
}) {
  const path = importBase(company) + '/simple-product-imports/' + job.id;
  const read = useServiceRead<Progress>(
    path + '/progress',
    productImportRequest,
    (value) => verify(value, job.id),
  );
  const [latest, setLatest] = useState<Progress | null>(null),
    [failure, setFailure] = useState<RequestFailure | null>(null),
    [running, setRunning] = useState(false),
    [refresh, setRefresh] = useState(0);
  const busy = useRef(false),
    mounted = useRef(true),
    permission = useRef(canManage);
  const queuedRequest = useRef<ServiceRequest | null>(null);
  permission.current = canManage;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const progress =
    latest &&
    (!read.data || latest.job.row_version >= read.data.job.row_version)
      ? latest
      : read.data;
  useEffect(() => {
    if (progress) onPending(progress.pending_count > 0);
  }, [progress?.pending_count]);
  useEffect(() => {
    if (
      !progress ||
      progress.job.id !== job.id ||
      progress.job.row_version < job.row_version
    )
      return;
    if (progress.job.row_version > job.row_version) onJob(progress.job);
    if (
      progress.job.state === 'SUCCEEDED' ||
      (progress.job.state === 'READY' &&
        (!queuedRequest.current ||
          queuedRequest.current.path.endsWith('/validate')))
    ) {
      queuedRequest.current = null;
      setFailure(null);
    }
  }, [progress, job.id, job.row_version, onJob]);
  async function resume() {
    if (busy.current || !permission.current) return;
    busy.current = true;
    setRunning(true);
    setFailure(null);
    try {
      let currentJob =
        progress && progress.job.row_version > job.row_version
          ? progress.job
          : job;
      // Every call resumes persisted native commands. Leaving the page is safe;
      // history can resume the same receipts after a lost response.
      for (
        let count = 0;
        count < 400 && mounted.current && permission.current;
        count++
      ) {
        let value: Progress;
        if (
          queuedRequest.current ||
          ['IMPORTING', 'VALIDATING'].includes(currentJob.state)
        ) {
          queuedRequest.current ??= {
            path:
              importBase(company) +
              '/import-jobs/' +
              job.id +
              (currentJob.state === 'VALIDATING' ? '/validate' : '/commit'),
            method: 'POST',
            key: crypto.randomUUID(),
            body: {
              expected_version: currentJob.row_version,
              ...(currentJob.state === 'IMPORTING'
                ? { review_digest: currentJob.review_digest }
                : {}),
            },
          };
          const saved = await productImportRequest<ImportJob>(
            queuedRequest.current,
          );
          assertImportJob(saved, job.id, 'simple_products');
          queuedRequest.current = null;
          value = await productImportRequest<Progress>({
            path: path + '/progress',
          });
        } else
          value = await productImportRequest<Progress>({
            path: path + '/advance',
            method: 'POST',
            body: {},
          });
        verify(value, job.id);
        currentJob = value.job;
        if (!mounted.current) break;
        setLatest(value);
        onJob(value.job);
        setRefresh((n) => n + 1);
        if (!value.can_resume || value.failed_count >= value.pending_count)
          break;
      }
    } catch (error) {
      const problem = requestFailure(error, 'product import');
      if (
        problem.status < 500 &&
        ![408, 429].includes(problem.status) &&
        !(
          problem.status === 409 &&
          problem.message.includes('retry with the same idempotency key')
        )
      )
        queuedRequest.current = null;
      if (mounted.current) setFailure(problem);
    } finally {
      busy.current = false;
      if (mounted.current) {
        setRunning(false);
        read.refresh();
        setRefresh((n) => n + 1);
      }
    }
  }
  useEffect(() => {
    if (autoRun && canManage) {
      onStarted();
      void resume();
    }
  }, [autoRun, canManage]);
  return (
    <Card>
      <CardHeader title="Product results" />
      <CardBody>
        <div className="janso-flow">
          <ProductCatalogFailure
            failure={failure ?? read.failure}
            retry={read.refresh}
          />
          {running && (
            <p role="status">
              {job.state === 'VALIDATING'
                ? 'Validating products…'
                : 'Creating products and posting opening stock…'}{' '}
              Progress is saved. You can resume from import history.
            </p>
          )}
          {!!progress?.pending_count && (
            <Notice tone={progress.failed_count ? 'warning' : 'info'}>
              {progress.pending_count}{' '}
              {progress.pending_count === 1
                ? 'product still needs'
                : 'products still need'}{' '}
              processing.{' '}
              {progress.failed_count
                ? 'Review the row messages, resolve the reported issue, then resume.'
                : 'Completed products will not be created again.'}
            </Notice>
          )}
          {canManage && (progress?.can_resume || failure) && (
            <div className="janso-form-actions">
              <Button
                loading={running}
                disabled={running}
                onClick={() => void resume()}
              >
                {job.state === 'VALIDATING'
                  ? 'Resume validation'
                  : 'Resume import'}
              </Button>
            </div>
          )}
          <ProductRows key={job.row_version + ':' + refresh} path={path} />
        </div>
      </CardBody>
    </Card>
  );
}

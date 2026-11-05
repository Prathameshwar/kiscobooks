'use client';
import type { components } from '@janso/api-client/catalog';
import { serviceCall, type ServiceRequest } from './service-call';
import { sessionFetch } from './session-fetch';
import { useState } from 'react';
import {
  useServiceRead,
  type ServicePage,
  type ServiceReader,
} from './service-resource';

export type ImportJob = components['schemas']['ImportDetail'];
export type ImportJobItem = components['schemas']['ImportJobListItem'];
export type ImportTemplate = components['schemas']['TemplateDetail'];
export type ImportDefinitions = components['schemas']['ImportDefinitions'];
export type ImportRecord = components['schemas']['ImportRecordItem'];
export type ImportAttempt = components['schemas']['ImportAttemptItem'];
export type ImportIssue = components['schemas']['ImportIssueItem'];
export type ImportArtifact = components['schemas']['ImportArtifactItem'];
export type ImportRevision = components['schemas']['ImportRevisionItem'];
export type ImportFormat = components['schemas']['SourceFile']['format'];
export type StageImport = components['schemas']['StageImport'];
export type ImportDownload = components['schemas']['DownloadOptions'];
export const importMaximumBytes = 8 * 1024 * 1024,
  importMaximumFiles = 16;
export const importId = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const productImportRequest = <T>(request: ServiceRequest) =>
  serviceCall<T>(
    '/api/product-import',
    { ...request, service: 'catalog' },
    'product import',
  );
export const importBase = (company: string) => '/v1/companies/' + company;
/** Import history uses its own ascending signed cursors and does not admit a sort query. */
export function useImportList<T extends { id: string }>(
  base: string | undefined,
  reader: ServiceReader = productImportRequest,
) {
  const [position, setPosition] = useState<{
    base?: string;
    cursor: string | null;
    previous: (string | null)[];
  }>({ base, cursor: null, previous: [] });
  const current =
    position.base === base ? position : { base, cursor: null, previous: [] };
  const query = new URLSearchParams({ limit: '25' });
  if (current.cursor) query.set('cursor', current.cursor);
  const read = useServiceRead<ServicePage<T>>(
    base ? base + '?' + query : undefined,
    reader,
    (value) => {
      if (
        !Array.isArray(value.items) ||
        value.items.some((row) => !row || !importId.test(row.id)) ||
        !value.page ||
        !Number.isInteger(value.page.limit) ||
        typeof value.page.has_more !== 'boolean' ||
        (value.page.has_more && !value.page.next_cursor)
      )
        throw { status: 502, message: 'Import history could not be verified.' };
    },
  );
  return {
    ...read,
    limit: 25,
    hasPrevious: current.previous.length > 0,
    next() {
      if (
        !read.loading &&
        read.data?.page.has_more &&
        read.data.page.next_cursor
      )
        setPosition({
          base,
          cursor: read.data.page.next_cursor,
          previous: [...current.previous, current.cursor],
        });
    },
    previous() {
      if (!read.loading && current.previous.length)
        setPosition({
          base,
          cursor: current.previous.at(-1) ?? null,
          previous: current.previous.slice(0, -1),
        });
    },
    first() {
      setPosition({ base, cursor: null, previous: [] });
      read.refresh();
    },
  };
}
export function assertImportJob(
  value: ImportJob,
  id?: string,
  definition = 'products',
): void {
  if (
    !value ||
    !importId.test(value.id) ||
    (id && value.id !== id) ||
    value.definition !== definition ||
    !Number.isSafeInteger(value.row_version) ||
    value.row_version < 1 ||
    !Number.isSafeInteger(value.revision) ||
    value.revision < 1 ||
    !Number.isFinite(Date.parse(value.expires_at)) ||
    (value.review_digest !== null &&
      !/^[0-9a-f]{64}$/.test(value.review_digest)) ||
    (['READY', 'IMPORTING'].includes(value.state) && !value.review_digest) ||
    !Number.isSafeInteger(value.record_count) ||
    value.record_count < 0 ||
    !Number.isSafeInteger(value.completed_count) ||
    value.completed_count < 0 ||
    value.completed_count > value.record_count ||
    ![
      'STAGED',
      'VALIDATING',
      'IMPORTING',
      'INVALID',
      'READY',
      'SUCCEEDED',
      'PARTIAL',
      'FAILED',
      'CANCELLED',
      'EXPIRED',
    ].includes(value.state)
  )
    throw {
      status: 502,
      message:
        'This product import could not be verified. Reload its history before continuing.',
    };
}
export function assertImportTemplate(
  value: ImportTemplate,
  definition = 'products',
): void {
  if (
    !value ||
    !importId.test(value.id) ||
    value.definition !== definition ||
    !value.snapshot ||
    typeof value.snapshot.schemas !== 'object' ||
    !value.snapshot.schemas ||
    !Number.isFinite(Date.parse(value.expires_at))
  )
    throw {
      status: 502,
      message: 'The product template could not be verified.',
    };
}
export function importFileProblem(files: readonly File[]): string | undefined {
  if (!files.length) return 'Choose at least one import file.';
  if (files.length > importMaximumFiles) return 'Choose at most 16 files.';
  if (files.some((file) => !/\.(csv|tsv|xlsx)$/i.test(file.name)))
    return 'Use CSV, TSV or XLSX files. Legacy XLS files are not supported.';
  if (files.some((file) => !file.size))
    return 'Empty files cannot be imported.';
  if (files.reduce((sum, file) => sum + file.size, 0) > importMaximumBytes)
    return 'The combined file size must not exceed 8 MB.';
}
export async function importSourceFiles(
  files: readonly File[],
): Promise<StageImport['files']> {
  const problem = importFileProblem(files);
  if (problem) throw { status: 422, message: problem };
  return Promise.all(
    files.map(async (file, index) => {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const value = String(reader.result ?? '');
          value.includes(',')
            ? resolve(value.slice(value.indexOf(',') + 1))
            : reject(new Error('File could not be read.'));
        };
        reader.onerror = () =>
          reject(new Error('File could not be read. Choose the file again.'));
        reader.readAsDataURL(file);
      });
      const suffix = file.name.split('.').at(-1)!.toLowerCase();
      const stem =
        file.name
          .slice(0, -suffix.length - 1)
          .replace(/[^A-Za-z0-9_.-]/g, '-')
          .replace(/^[^A-Za-z0-9]+/, '')
          .slice(0, 96) || 'products';
      return {
        filename: `${index + 1}-${stem}.${suffix}`,
        format: suffix.toUpperCase() as ImportFormat,
        content_base64: content,
      };
    }),
  );
}
export const importStateLabel = (state: string) =>
  (
    ({
      STAGED: 'Awaiting validation',
      VALIDATING: 'Validating',
      IMPORTING: 'Preparing products',
      PENDING: 'Processing',
      QUEUED: 'Waiting',
      INVALID: 'Needs correction',
      READY: 'Ready to import',
      SUCCEEDED: 'Completed',
      PARTIAL: 'Partially imported',
      FAILED: 'Import failed',
      CANCELLED: 'Cancelled',
      EXPIRED: 'Expired',
      VALID: 'Valid',
      APPLIED: 'Imported',
      SKIPPED: 'Skipped',
      BLOCKED: 'Blocked',
      VALIDATED: 'Valid',
    }) as Record<string, string>
  )[state] ?? state.replaceAll('_', ' ').toLowerCase();
export const importStateTone = (
  state: string,
): 'success' | 'warn' | 'danger' | 'neutral' =>
  ['SUCCEEDED', 'APPLIED', 'VALID'].includes(state)
    ? 'success'
    : ['INVALID', 'FAILED'].includes(state)
      ? 'danger'
      : ['PARTIAL', 'BLOCKED'].includes(state)
        ? 'warn'
        : 'neutral';
export async function downloadProductImport(
  request: ServiceRequest,
  filename: string,
): Promise<void> {
  return downloadMasterImport(
    '/api/product-import',
    'catalog',
    request,
    filename,
  );
}
export async function downloadMasterImport(
  endpoint: string,
  service: 'catalog' | 'accounting',
  request: ServiceRequest,
  filename: string,
): Promise<void> {
  const response = await sessionFetch(
    endpoint,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...request,
        service,
        method: request.method ?? 'GET',
      }),
    },
    !request.method || request.method === 'GET' || !!request.key,
  );
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    throw {
      status: response.status,
      message:
        value?.error?.message ?? 'The import file could not be downloaded.',
    };
  }
  const media = response.headers.get('content-type')?.split(';')[0];
  if (
    ![
      'text/csv',
      'text/tab-separated-values',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/octet-stream',
    ].includes(media ?? '')
  )
    throw {
      status: 502,
      message: 'The download response was not an import file.',
    };
  const url = URL.createObjectURL(await response.blob()),
    link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

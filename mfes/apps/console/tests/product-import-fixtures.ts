import type { ImportJob, ImportTemplate } from '../app/lib/product-import';
export const COMPANY = '01990000-0000-7000-8000-000000000001',
  JOB = '01990000-0000-7000-8000-000000000002',
  TEMPLATE = '01990000-0000-7000-8000-000000000003',
  ATTEMPT = '01990000-0000-7000-8000-000000000004',
  ROW = '01990000-0000-7000-8000-000000000005',
  REVISION = '01990000-0000-7000-8000-000000000006';
export const page = { limit: 25, has_more: false, next_cursor: null };
export const template: ImportTemplate = {
  id: TEMPLATE,
  definition: 'products',
  fingerprint: 'a'.repeat(64),
  expires_at: '2099-01-01T00:00:00Z',
  snapshot: {
    schemas: {
      'product_family:CREATE': {
        properties: {
          code: { title: 'Code', type: 'string' },
          name: { title: 'Name', type: 'string' },
        },
        required: ['code', 'name'],
      },
      'product_family:UPDATE': {
        properties: { name: { title: 'Name', type: 'string' } },
      },
      'item:UPDATE': { properties: { sku: { type: 'string' } } },
    },
  },
};
export function job(state = 'STAGED', version = 1): ImportJob {
  return {
    id: JOB,
    definition: 'products',
    state,
    revision: 1,
    row_version: version,
    record_count: 1,
    completed_count: state === 'SUCCEEDED' ? 1 : 0,
    review_digest: state === 'READY' ? 'b'.repeat(64) : null,
    expires_at: '2099-01-01T00:00:00Z',
    created_at: '2026-10-27T00:00:00Z',
  };
}
export function importResponse(path: string, current = job()) {
  if (path.includes('import-definitions'))
    return {
      items: [{ key: 'products', label: 'Products and services' }],
      formats: ['CSV', 'TSV', 'XLSX'],
      maximum_commands: 200,
    };
  if (path.includes('/import-templates')) return template;
  if (path.includes('/history/attempts'))
    return {
      items:
        current.state === 'STAGED'
          ? []
          : [
              {
                id: ATTEMPT,
                revision_id: REVISION,
                phase: 'VALIDATE',
                outcome: current.state === 'INVALID' ? 'FAILED' : 'SUCCEEDED',
                created_at: current.created_at,
                finished_at: current.created_at,
              },
            ],
      page,
    };
  if (path.includes('/history/revisions'))
    return {
      items: [
        {
          id: REVISION,
          revision: 1,
          input_hash: 'c'.repeat(64),
          created_at: current.created_at,
        },
      ],
      page,
    };
  if (path.includes('/history/artifacts')) return { items: [], page };
  if (path.includes('/issues'))
    return {
      items:
        current.state === 'INVALID'
          ? [
              {
                id: ATTEMPT,
                record_id: ROW,
                field: 'name',
                code: 'missing',
                message: 'Required field is missing.',
              },
            ]
          : [],
      page,
    };
  if (path.includes('/records'))
    return {
      items: [
        {
          id: ROW,
          logical_key: 'product-1',
          resource: 'product_family',
          source_file: '1-products.csv',
          source_sheet: 'Records',
          source_row: 3,
          status:
            current.state === 'STAGED'
              ? null
              : current.state === 'INVALID'
                ? 'INVALID'
                : current.state === 'SUCCEEDED'
                  ? 'APPLIED'
                  : 'VALID',
          business_id: current.state === 'SUCCEEDED' ? TEMPLATE : null,
        },
      ],
      page,
    };
  if (path.includes('/download-ticket'))
    return { token: 'private-ticket', expires_in: 300 };
  if (/\/import-jobs\?/.test(path)) return { items: [current], page };
  return current;
}

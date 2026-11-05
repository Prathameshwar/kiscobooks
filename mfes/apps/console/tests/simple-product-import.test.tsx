import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductImport } from '../app/components/ProductImport';
import { useProductMode } from '../app/components/ProductModeProvider';
import { serviceCall } from '../app/lib/service-call';
import { downloadProductImport } from '../app/lib/product-import';
import {
  COMPANY,
  JOB,
  ROW,
  importResponse,
  job,
  page,
  template,
} from './product-import-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({
  useProductMode: vi.fn(),
}));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/product-import', async (original) => ({
  ...(await original<typeof import('../app/lib/product-import')>()),
  downloadProductImport: vi.fn(),
}));
const api = vi.mocked(serviceCall);
const simpleJob = (state = 'STAGED', version = 1) => ({
  ...job(state, version),
  definition: 'simple_products',
});
let current = simpleJob();
let lost = false;
beforeEach(() => {
  vi.clearAllMocks();
  lost = false;
  current = simpleJob();
  window.history.replaceState(null, '', '/masters/items/import');
  vi.mocked(useProductMode).mockReturnValue({
    company: COMPANY,
    data: {
      company_id: COMPANY,
      product_family_sku_enabled: false,
      row_version: 1,
      policy_generation: 1,
    },
    loading: false,
    failure: null,
    refresh: vi.fn(),
  });
  api.mockImplementation(async (_, request) => {
    const path = request.path;
    if (path.includes('/import-definitions'))
      return {
        items: [{ key: 'simple_products' }],
        formats: ['CSV', 'TSV', 'XLSX'],
        maximum_commands: 200,
      } as never;
    if (path.includes('/import-templates'))
      return {
        ...template,
        definition: 'simple_products',
        snapshot: {
          schemas: {
            'simple_product_create:CREATE': {
              properties: {
                name: { type: 'string' },
                code: { type: 'string' },
                base_unit: { type: 'string' },
              },
              required: ['name', 'base_unit'],
            },
          },
        },
      } as never;
    if (path.endsWith('/validate')) current = simpleJob('READY', 2);
    if (path.endsWith('/commit')) current = simpleJob('PARTIAL', 3);
    if (path.endsWith('/advance')) {
      if (lost) {
        lost = false;
        throw {
          status: 503,
          message: 'Connection interrupted. Resume the same import.',
        };
      }
      current = simpleJob('SUCCEEDED', 4);
    }
    if (path.includes('/simple-product-imports/')) {
      if (path.includes('/rows'))
        return {
          items: [
            {
              id: ROW,
              source_file: 'products.csv',
              source_row: 3,
              code: current.state === 'SUCCEEDED' ? 'AUTO123456' : null,
              name: 'Imported product',
              state: current.state === 'SUCCEEDED' ? 'APPLIED' : 'PENDING',
              step: 'CREATE',
              opening_posted: current.state === 'SUCCEEDED',
              messages: [],
            },
          ],
          page,
        } as never;
      return {
        job: current,
        pending_count: ['PARTIAL', 'IMPORTING', 'VALIDATING'].includes(
          current.state,
        )
          ? 1
          : 0,
        failed_count: 0,
        can_resume: ['PARTIAL', 'IMPORTING', 'VALIDATING'].includes(
          current.state,
        ),
      } as never;
    }
    return importResponse(path, current) as never;
  });
});

it.each([408, 429])('recovers the initial import action with the same request after HTTP %s', async status => {
  current = simpleJob('READY', 2);
  const ordinary = api.getMockImplementation()!;
  let commits = 0;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/commit') && ++commits === 1) throw { status, message: 'Import admission could not be confirmed.' };
    return ordinary(endpoint, request, subject);
  });
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await user.click(await screen.findByRole('button', { name: 'Review import' }));
  const dialog = await screen.findByRole('dialog', { name: 'Import validated products?' });
  await user.click(within(dialog).getByRole('button', { name: 'Import products' }));
  await user.click(await screen.findByRole('button', { name: 'Retry same action' }));
  await screen.findByText('AUTO123456');
  const requests = api.mock.calls.filter(([, request]) => request.path.endsWith('/commit'));
  expect(requests).toHaveLength(2); expect(requests[1]![1]).toEqual(requests[0]![1]);
});

it('shows barcode columns and their required status from the configured template', async () => {
  const ordinary = api.getMockImplementation()!;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.includes('/import-templates')) return { ...template, definition: 'simple_products', snapshot: {
      schemas: { 'simple_product_create:CREATE': { properties: {
        barcode_value: { type: 'string', title: 'Barcode value' }, barcode_symbology: { type: 'string', title: 'Barcode format', description: 'Blank uses CODE128.' },
      }, required: ['barcode_value'] } },
    } } as never;
    return ordinary(endpoint, request, subject);
  });
  render(<ProductImport company={COMPANY} canManage />);
  await userEvent.click(await screen.findByRole('button', { name: 'Download template' }));
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  await userEvent.click(screen.getByText('Template column guide'));
  expect(screen.getByText('barcode_value')).toBeVisible();
  expect(screen.getByText('barcode_symbology')).toBeVisible();
  expect(within(screen.getByText('barcode_value').closest('tr')!).getByText('Required')).toBeVisible();
});

it('shows configured selling-price names and required coverage in the template guide', async () => {
  const ordinary = api.getMockImplementation()!;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.includes('/import-templates')) return { ...template, definition: 'simple_products', snapshot: {
      schemas: { 'simple_product_create:CREATE': { properties: {
        sale_price_1: { type: 'string', title: 'Retail selling price', description: 'Including tax. Amount per base unit in INR.' },
        sale_price_2: { type: 'string', title: 'Wholesale selling price', description: 'Excluding tax. Amount per base unit in INR.' },
      }, required: ['sale_price_1'] } },
    } } as never;
    return ordinary(endpoint, request, subject);
  });
  render(<ProductImport company={COMPANY} canManage />);
  await userEvent.click(await screen.findByRole('button', { name: 'Download template' }));
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  await userEvent.click(screen.getByText('Template column guide'));
  const retail = within(screen.getByText('sale_price_1').closest('tr')!);
  const wholesale = within(screen.getByText('sale_price_2').closest('tr')!);
  expect(retail.getByText('Retail selling price')).toBeVisible();
  expect(retail.getByText('Required')).toBeVisible();
  expect(wholesale.getByText('Wholesale selling price')).toBeVisible();
  expect(wholesale.getByText('Optional')).toBeVisible();
});

it('continues other products after a row fails, then leaves the failed row resumable', async () => {
  current = simpleJob('PARTIAL', 3);
  const fallback = api.getMockImplementation()!;
  let advances = 0;
  api.mockImplementation(async (service, request, options) => {
    if (request.path.endsWith('/advance')) advances++;
    if (request.path.endsWith('/advance') || request.path.endsWith('/progress'))
      return {
        job: {
          ...current,
          row_version: 3 + advances,
          record_count: 2,
          completed_count: advances >= 2 ? 1 : 0,
        },
        pending_count: advances >= 2 ? 1 : 2,
        failed_count: advances > 0 ? 1 : 0,
        can_resume: true,
      } as never;
    return fallback(service, request, options);
  });
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Resume import' }),
  );
  await waitFor(() => expect(advances).toBe(2));
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Resume import' })).toBeEnabled(),
  );
  expect(advances).toBe(2);
});

it('identifies historical validation messages by their file and row', async () => {
  current = simpleJob('INVALID', 2);
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  expect(await screen.findByText('Required field is missing.')).toBeVisible();
  expect(
    await screen.findByText('1-products.csv · Records row 3 · product-1'),
  ).toBeVisible();
  expect(screen.queryByText(/^Row reference /)).not.toBeInTheDocument();
});

it('uses a flat current-config template and runs a validated import to readiness', async () => {
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage />);
  await user.selectOptions(
    await screen.findByRole('combobox', { name: 'Type' }),
    'SERVICE',
  );
  expect(screen.queryByLabelText('Configuration date')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Import operation')).not.toBeInTheDocument();
  expect(screen.queryByText('Import behaviour')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Download template' }));
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  expect(
    api.mock.calls.find(([, r]) => r.path.endsWith('/import-templates'))?.[1]
      .body,
  ).toEqual({
    definition: 'simple_products',
    parameters: { resource: 'simple_product_create', kind: 'SERVICE' },
  });
  await user.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(
      ['_import_schema_version,1\nname,base_unit\nImported product,HOUR'],
      'products.csv',
      { type: 'text/csv' },
    ),
  );
  await user.click(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  );
  await user.click(
    await screen.findByRole('button', { name: 'Validate files' }),
  );
  await user.click(
    await screen.findByRole('button', { name: 'Review import' }),
  );
  const dialog = await screen.findByRole('dialog', {
    name: 'Import validated products?',
  });
  await user.click(
    within(dialog).getByRole('button', { name: 'Import products' }),
  );
  await screen.findByText(
    'Import complete. All products are active and ready, and any opening stock has been posted.',
  );
  expect(
    screen.queryByText(
      'Import started. Product readiness and opening stock are being processed.',
    ),
  ).not.toBeInTheDocument();
  expect(await screen.findByText('AUTO123456')).toBeVisible();
  expect(screen.getByText('Posted', { exact: true })).toBeVisible();
  expect(
    api.mock.calls.filter(([, r]) => r.path.endsWith('/advance')),
  ).toHaveLength(1);
});

it('resumes retained commands after file expiry and a lost response without offering replacement or cancellation', async () => {
  current = { ...simpleJob('PARTIAL', 3), expires_at: '2020-01-01T00:00:00Z' };
  lost = true;
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  const resume = await screen.findByRole('button', { name: 'Resume import' });
  expect(api.mock.calls.some(([, r]) => r.path.endsWith('/advance'))).toBe(
    false,
  );
  expect(
    screen.queryByRole('button', { name: 'Cancel import' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByLabelText('Corrected import files'),
  ).not.toBeInTheDocument();
  await user.click(resume);
  await screen.findByText('Connection interrupted. Resume the same import.');
  await user.click(screen.getByRole('button', { name: 'Resume import' }));
  await screen.findByText('AUTO123456');
  expect(
    api.mock.calls.filter(([, r]) => r.path.endsWith('/advance')),
  ).toHaveLength(2);
  expect(api.mock.calls.some(([, r]) => r.path.endsWith('/commit'))).toBe(
    false,
  );
});

it('refreshes the completed page after the final server response is lost without another write', async () => {
  current = simpleJob('PARTIAL', 3);
  const ordinary = api.getMockImplementation()!;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/advance')) {
      current = simpleJob('SUCCEEDED', 4);
      throw { status: 503, message: 'The final response was lost.' };
    }
    return ordinary(endpoint, request, subject);
  });
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await userEvent.click(
    await screen.findByRole(
      'button',
      { name: 'Resume import' },
      { timeout: 5000 },
    ),
  );
  expect(
    await screen.findByText(
      'Import complete. All products are active and ready, and any opening stock has been posted.',
    ),
  ).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Resume import' }),
  ).not.toBeInTheDocument();
  expect(
    api.mock.calls.filter(([, request]) => request.path.endsWith('/advance')),
  ).toHaveLength(1);
});

it('shows results without mutation controls to readers', async () => {
  current = simpleJob('PARTIAL', 3);
  render(
    <ProductImport company={COMPANY} canManage={false} initialJob={JOB} />,
  );
  await screen.findByText('Imported product');
  expect(
    screen.queryByRole('button', { name: 'Resume import' }),
  ).not.toBeInTheDocument();
  expect(api.mock.calls.some(([, r]) => r.method === 'POST')).toBe(false);
});

it('continues bounded validation automatically and retains a resumable admission request', async () => {
  current = simpleJob('STAGED', 1);
  const ordinary = api.getMockImplementation()!;
  let validations = 0;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/validate')) {
      current = simpleJob(
        ++validations === 1 ? 'VALIDATING' : 'READY',
        validations + 1,
      );
      return current as never;
    }
    return ordinary(endpoint, request, subject);
  });
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await user.click(
    await screen.findByRole('button', { name: 'Validate files' }),
  );
  expect(
    await screen.findByRole('button', { name: 'Review import' }),
  ).toBeEnabled();
  expect(validations).toBe(2);
});

it('retries interrupted admission with its exact body and idempotency key before processing products', async () => {
  current = { ...simpleJob('IMPORTING', 3), review_digest: 'b'.repeat(64) };
  const ordinary = api.getMockImplementation()!;
  let failed = false;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/commit') && !failed) {
      failed = true;
      throw { status: 503, message: 'Admission response was interrupted.' };
    }
    return ordinary(endpoint, request, subject);
  });
  const user = userEvent.setup();
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await user.click(
    await screen.findByRole('button', { name: 'Resume import' }),
  );
  await screen.findByText('Admission response was interrupted.');
  await user.click(screen.getByRole('button', { name: 'Resume import' }));
  await screen.findByText('AUTO123456');
  const requests = api.mock.calls
    .filter(([, r]) => r.path.endsWith('/commit'))
    .map(([, r]) => r);
  expect(requests).toHaveLength(2);
  expect(requests[0]?.key).toBeTruthy();
  expect(requests[1]).toEqual(requests[0]);
});

it('retains earlier draft-import history as read-only in Simple mode', async () => {
  current = job('READY', 2);
  api.mockImplementation(
    async (_, r) => importResponse(r.path, current) as never,
  );
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await screen.findByText(
    /This earlier import uses the draft product workflow/,
  );
  expect(
    screen.queryByRole('button', { name: 'Review import' }),
  ).not.toBeInTheDocument();
  expect(
    await screen.findByRole('button', { name: 'Download results' }),
  ).toBeEnabled();
});

it.each([503, 408, 429])('preserves the admission retry after an uncertain %s response and a refresh', async status => {
  current = { ...simpleJob('IMPORTING', 3), review_digest: 'b'.repeat(64) };
  const ordinary = api.getMockImplementation()!;
  let commits = 0;
  api.mockImplementation(async (endpoint, request, subject) => {
    if (request.path.endsWith('/commit')) {
      current = simpleJob('PARTIAL', 4);
      if (++commits === 1)
        throw {
          status,
          message: 'Committed admission response was lost.',
        };
      return current as never;
    }
    return ordinary(endpoint, request, subject);
  });
  render(<ProductImport company={COMPANY} canManage initialJob={JOB} />);
  await userEvent.click(
    await screen.findByRole('button', { name: 'Resume import' }),
  );
  await screen.findByText('Committed admission response was lost.');
  await userEvent.click(screen.getByRole('button', { name: 'Resume import' }));
  await screen.findByText(
    'Import complete. All products are active and ready, and any opening stock has been posted.',
  );
  const requests = api.mock.calls.filter(([, request]) =>
    request.path.endsWith('/commit'),
  );
  expect(requests).toHaveLength(2);
  expect(requests[1]![1]).toEqual(requests[0]![1]);
  expect(
    api.mock.calls.filter(([, request]) => request.path.endsWith('/advance')),
  ).toHaveLength(1);
});

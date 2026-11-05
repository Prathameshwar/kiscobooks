import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductImport } from '../app/components/ProductImport';
import { serviceCall } from '../app/lib/service-call';
import { downloadProductImport } from '../app/lib/product-import';
import {
  COMPANY,
  JOB,
  importResponse,
  job,
  page,
} from './product-import-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/product-import', async (original) => ({
  ...(await original<typeof import('../app/lib/product-import')>()),
  downloadProductImport: vi.fn(),
}));
const api = vi.mocked(serviceCall);
let current = job();
beforeEach(() => {
  vi.clearAllMocks();
  current = job();
  window.history.replaceState(null, '', '/masters/items/import');
  api.mockImplementation(async (_, request) => {
    if (request.method === 'POST' && request.path.endsWith('/validate'))
      current = job('READY', 2);
    if (request.method === 'POST' && request.path.endsWith('/commit'))
      current = job('SUCCEEDED', 3);
    return importResponse(request.path, current) as never;
  });
});
const show = (props = {}) =>
  render(<ProductImport company={COMPANY} canManage {...props} />);
async function templateAndFile() {
  await userEvent.click(
    await screen.findByRole('button', { name: 'Download template' }),
  );
  await waitFor(() => expect(downloadProductImport).toHaveBeenCalled());
  await userEvent.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(
      [
        '_import_schema_version,1\n_key,_set,_resource,_action,name\nrow,group,product_family,AUTO,Example',
      ],
      'products.csv',
      { type: 'text/csv' },
    ),
  );
}
it('uses shared page, form, upload and progress layouts', async () => {
  show();
  expect(
    await screen.findByRole('button', { name: 'Download template' }),
  ).toBeEnabled();
  expect(
    screen.getByRole('navigation', { name: 'Setup progress' }),
  ).toBeInTheDocument();
  expect(screen.getByRole('tabpanel')).toHaveAccessibleName('New import');
  expect(
    screen
      .getByRole('heading', { name: '1. Choose a product template' })
      .closest('.janso-card'),
  ).not.toBeNull();
});
it('stages uploaded files and validates before allowing a reviewed import', async () => {
  show();
  await templateAndFile();
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  );
  await screen.findByRole('button', { name: 'Validate files' });
  expect(
    api.mock.calls.some(([, request]) => request.path.endsWith('/commit')),
  ).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Validate files' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Review import' }),
  );
  const confirmation = await screen.findByRole('dialog', {
    name: 'Import validated products?',
  });
  await userEvent.click(
    within(confirmation).getByRole('button', { name: 'Import products' }),
  );
  await screen.findByText(
    'Product import completed successfully. Review the results below or return to the product directory.',
  );
  const commit = api.mock.calls.find(([, request]) =>
    request.path.endsWith('/commit'),
  )![1];
  expect(commit.body).toEqual({
    expected_version: 2,
    review_digest: 'b'.repeat(64),
  });
  expect(commit.key).toBeTruthy();
  expect(
    screen.queryByRole('button', { name: 'Review import' }),
  ).not.toBeInTheDocument();
});
it('shows invalid row messages and permits a corrected revision', async () => {
  current = job('INVALID', 2);
  show({ initialJob: JOB });
  expect(await screen.findByText('Required field is missing.')).toBeVisible();
  expect(
    screen.queryByRole('button', { name: 'Review import' }),
  ).not.toBeInTheDocument();
  await userEvent.upload(
    document.querySelector<HTMLInputElement>('input[type=file]')!,
    new File(['corrected'], 'corrected.csv', { type: 'text/csv' }),
  );
  expect(
    screen.getByRole('button', { name: 'Revalidate remaining work' }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload corrected revision' }),
  );
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.endsWith('/revisions') && request.method === 'POST',
      ),
    ).toBe(true),
  );
  const correction = api.mock.calls.find(
    ([, request]) =>
      request.path.endsWith('/revisions') && request.method === 'POST',
  )![1];
  expect(correction.body).toMatchObject({
    expected_version: 2,
    files: [{ format: 'CSV' }],
  });
});

it('binds an original source download to its historical file revision', async () => {
  current = { ...job('INVALID', 2), revision: 2 };
  api.mockImplementation(async (_, request) =>
    request.path.includes('/history/artifacts')
      ? ({
          items: [
            {
              id: JOB,
              revision_id: '01990000-0000-7000-8000-000000000006',
              filename: 'original.csv',
              format: 'CSV',
              byte_count: 20,
              content_sha256: 'a'.repeat(64),
              expires_at: '2099-01-01T00:00:00Z',
            },
          ],
          page,
        } as never)
      : (importResponse(request.path, current) as never),
  );
  show({ initialJob: JOB });
  await userEvent.click(
    await screen.findByText('Source files and file revisions'),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Download source' }),
  );
  await waitFor(() =>
    expect(
      api.mock.calls.some(([, request]) =>
        request.path.endsWith('/download-ticket'),
      ),
    ).toBe(true),
  );
  const ticket = api.mock.calls.find(([, request]) =>
    request.path.endsWith('/download-ticket'),
  )![1];
  expect(ticket.body).toMatchObject({
    artifact_id: JOB,
    revision: 1,
    kind: 'SOURCE',
  });
});
it('recovers an uncertain stage with the exact same key and bytes', async () => {
  let lost = true;
  api.mockImplementation(async (_, request) => {
    if (
      request.method === 'POST' &&
      request.path.endsWith('/import-jobs') &&
      lost
    )
      throw { status: 503, message: 'Result unavailable' };
    return importResponse(request.path, current) as never;
  });
  show();
  await templateAndFile();
  await userEvent.click(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  );
  await screen.findByRole('button', { name: 'Retry same action' });
  expect(
    screen.getByRole('combobox', { name: 'Import content' }),
  ).toBeDisabled();
  lost = false;
  await userEvent.click(
    screen.getByRole('button', { name: 'Retry same action' }),
  );
  await screen.findByRole('button', { name: 'Validate files' });
  const writes = api.mock.calls.filter(
    ([, request]) =>
      request.method === 'POST' && request.path.endsWith('/import-jobs'),
  );
  expect(writes).toHaveLength(2);
  expect(writes[0]![1].key).toBe(writes[1]![1].key);
  expect(writes[0]![1].body).toEqual(writes[1]![1].body);
});
it('requires revalidation after a stale reviewed commit', async () => {
  current = job('READY', 2);
  api.mockImplementation(async (_, request) => {
    if (request.path.endsWith('/commit'))
      throw { status: 409, message: 'Configuration changed.' };
    return importResponse(request.path, current) as never;
  });
  show({ initialJob: JOB });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Review import' }),
  );
  await userEvent.click(
    within(await screen.findByRole('dialog')).getByRole('button', {
      name: 'Import products',
    }),
  );
  await screen.findByText('Configuration changed.');
  expect(screen.getByRole('button', { name: 'Review import' })).toBeDisabled();
  await userEvent.click(
    screen.getByRole('button', { name: 'Reload and review' }),
  );
  expect(screen.getByRole('button', { name: 'Review import' })).toBeDisabled();
});
it('keeps history read-only without import management access', async () => {
  current = job('READY', 2);
  show({ canManage: false, initialJob: JOB });
  await screen.findByRole('heading', { name: 'Review and continue' });
  expect(
    screen.queryByRole('button', { name: 'Review import' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: 'Upload corrected revision' }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('tab', { name: 'Import history' }));
  expect(
    await screen.findByRole('link', { name: /Open import/ }),
  ).toHaveAttribute('href', expect.stringContaining('job=' + JOB));
});
it('requires confirmation before cancelling and retains final history', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.path.endsWith('/cancel')) current = job('CANCELLED', 2);
    return importResponse(request.path, current) as never;
  });
  show({ initialJob: JOB });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Cancel import' }),
  );
  await userEvent.click(
    within(
      await screen.findByRole('dialog', { name: 'Cancel this import?' }),
    ).getByRole('button', { name: 'Cancel import now' }),
  );
  await screen.findByText(
    'This import is cancelled. Its history and any completed work are retained.',
  );
  expect(
    screen.queryByRole('button', { name: 'Cancel import' }),
  ).not.toBeInTheDocument();
});
it('keeps history paging when the current Catalog page has no products', async () => {
  api.mockImplementation(async (_, request) =>
    /\/import-jobs\?/.test(request.path)
      ? ({
          items: [{ ...job(), definition: 'prices' }],
          page: { ...page, has_more: true, next_cursor: 'signed-next' },
        } as never)
      : (importResponse(request.path, current) as never),
  );
  show({ initialHistory: true });
  await screen.findByText('No product imports on this page');
  await userEvent.click(
    screen.getByRole('button', { name: 'Next page of product imports' }),
  );
  await waitFor(() =>
    expect(
      api.mock.calls.some(([, request]) =>
        request.path.includes('cursor=signed-next'),
      ),
    ).toBe(true),
  );
  expect(
    api.mock.calls.every(([, request]) => !request.path.includes('sort=')),
  ).toBe(true);
});
it.each([
  ['Download results', 'RESULT'],
  ['Download staged input', 'NORMALIZED'],
])('downloads %s through a private ticket', async (label, kind) => {
  current = job('SUCCEEDED', 3);
  show({ initialJob: JOB });
  await userEvent.click(await screen.findByRole('button', { name: label }));
  await waitFor(() =>
    expect(downloadProductImport).toHaveBeenCalledWith(
      expect.objectContaining({
        method: 'POST',
        body: expect.objectContaining({
          token: 'private-ticket',
          kind,
        }),
      }),
      expect.any(String),
    ),
  );
});
it('revalidates remaining work in a partial import instead of repeating completed effects', async () => {
  current = { ...job('PARTIAL', 3), record_count: 2, completed_count: 1 };
  api.mockImplementation(async (_, request) => {
    if (request.path.endsWith('/retry'))
      current = { ...job('READY', 4), record_count: 2, completed_count: 1 };
    return importResponse(request.path, current) as never;
  });
  show({ initialJob: JOB });
  await userEvent.click(
    await screen.findByRole('button', { name: 'Revalidate remaining work' }),
  );
  await screen.findByRole('button', { name: 'Review import' });
  expect(
    api.mock.calls.find(([, request]) => request.path.endsWith('/retry'))![1]
      .body,
  ).toEqual({ expected_version: 3 });
  expect(
    api.mock.calls.some(([, request]) => request.path.endsWith('/commit')),
  ).toBe(false);
});
it('protects an unuploaded file when leaving the import page', async () => {
  show();
  await templateAndFile();
  await userEvent.click(screen.getByRole('link', { name: 'Back to products' }));
  expect(
    await screen.findByRole('dialog', { name: 'Discard unsaved changes?' }),
  ).toBeVisible();
  await userEvent.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }),
  );
  expect(
    screen.getByRole('button', { name: 'Upload and prepare validation' }),
  ).toBeEnabled();
  expect(
    screen.getByRole('combobox', { name: 'Import content' }),
  ).toBeDisabled();
});

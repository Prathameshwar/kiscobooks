import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OpeningStockImports } from '../app/components/OpeningStockImports';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import {
  access,
  COMPANY,
  JOB,
  control,
  manifest,
  page,
} from './opening-stock-fixtures';
import type { ImportJob } from '../app/lib/opening-stock';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
let state = 'READY';
const job = (): ImportJob => ({
  id: JOB,
  company_id: COMPANY,
  source_key: 'offline-opening',
  row_version: 2,
  state,
  review_hash: 'b'.repeat(64),
  input_hash: 'a'.repeat(64),
  chunk_count: 3,
  validated_chunks: 3,
  created_chunks: 0,
  effects: [],
  errors: [],
  effect_kind: 'DRAFT_ONLY',
  posting_required: true,
});
beforeEach(() => {
  state = 'READY';
  api.mockReset().mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/template'))
      return {
        marker: '_stock_opening_schema_version',
        version: 1,
        required_columns: ['source_key'],
        optional_columns: [],
        reference_policy: 'Native authorized IDs',
        effect: 'Creates native drafts only.',
      } as never;
    if (request.path.includes('?'))
      return {
        items: [
          { id: JOB, source_key: 'offline-opening', state, row_version: 2 },
        ],
        page,
      } as never;
    return job() as never;
  });
});
it('read-only import history does not call manager-only template or show creation controls', async () => {
  render(
    <OpeningStockImports
      company={COMPANY}
      access={{ ...access, draft: false, commit: false }}
      control={control}
      manifest={manifest}
      onChanged={() => {}}
    />,
  );
  await screen.findByRole('button', { name: 'offline-opening' });
  expect(
    api.mock.calls.some(([, request]) => request.path.endsWith('/template')),
  ).toBe(false);
  expect(screen.queryByLabelText('Import reference')).not.toBeInTheDocument();
});
it('reviews and commits only the selected native job version and review hash', async () => {
  render(
    <OpeningStockImports
      company={COMPANY}
      access={access}
      control={control}
      manifest={manifest}
      onChanged={() => {}}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'offline-opening' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Review and create drafts' }),
  );
  expect(screen.getByRole('dialog')).toHaveTextContent(
    'does not approve vouchers or post stock',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Create drafts' }));
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.endsWith('/commit') &&
          JSON.stringify(request.body) ===
            JSON.stringify({
              expected_version: 2,
              review_hash: 'b'.repeat(64),
            }),
      ),
    ).toBe(true),
  );
});
it('retains exact file staging bytes and key after a lost response', async () => {
  const original = api.getMockImplementation()!,
    writes: ServiceRequest[] = [];
  api.mockImplementation(async (...args) => {
    if (args[1].method === 'POST') {
      writes.push(args[1]);
      if (writes.length === 1)
        throw { status: 503, message: 'Lost staging response' };
      return { ...job(), state: 'STAGED' } as never;
    }
    return original(...args);
  });
  render(
    <OpeningStockImports
      company={COMPANY}
      access={access}
      control={control}
      manifest={manifest}
      onChanged={() => {}}
    />,
  );
  await screen.findByLabelText('Import reference');
  fireEvent.change(screen.getByLabelText('Import reference'), {
    target: { value: 'offline-opening' },
  });
  const file = new File(['{"vouchers":[]}'], 'opening.json', {
    type: 'application/json',
  });
  Object.defineProperty(file, 'text', { value: async () => '{"vouchers":[]}' });
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  await userEvent.upload(input, file);
  await userEvent.click(
    screen.getByRole('button', { name: 'Stage and inspect file' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry the same request' }),
  );
  await waitFor(() => expect(writes).toHaveLength(2));
  expect(writes[1]!.key).toBe(writes[0]!.key);
  expect(writes[1]!.body).toEqual(writes[0]!.body);
});
it('cancel confirmation explains already-created drafts are retained', async () => {
  state = 'COMMITTING';
  render(
    <OpeningStockImports
      company={COMPANY}
      access={access}
      control={control}
      manifest={manifest}
      onChanged={() => {}}
    />,
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'offline-opening' }),
  );
  await userEvent.click(
    await screen.findByRole('button', { name: 'Cancel remaining preparation' }),
  );
  expect(screen.getByRole('dialog')).toHaveTextContent(
    'Already created vouchers remain',
  );
});

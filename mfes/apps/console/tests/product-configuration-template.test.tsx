import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, SCOPE, revision, page, response } from './product-configuration-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
it('does not silently reset a nondefault published setting that the new draft cannot copy', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_, request) => {
    if (request.path.includes('/revisions?')) return { items: [revision], page } as never;
    const value = structuredClone(response(request.path, request.method)) as { fields?: { key: string; writable: boolean }[] };
    if (request.path.includes('catalog.product_entry_option_policy')) value.fields!.find(field => field.key === 'barcode_mode')!.writable = false;
    return value as never;
  });
  render(<ProductConfigurationEditor company={COMPANY} scopeId={SCOPE} timezone="Asia/Kolkata" />);
  expect(await screen.findByText(/Published settings cannot be copied completely/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
});

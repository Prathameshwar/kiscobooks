/**
 * The designer route offers the R4 Purchase flow — *Used for* and *Preview with a saved bill* —
 * only to whoever may use each piece, and only on a design Purchase can print from.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { DesignerRoute } from '../app/(editor)/invoice-designer/DesignerRoute';
import { layoutToWire } from '../app/lib/design-canvas';
import { standardPurchaseLayout } from '../app/(editor)/invoice-designer/standard-purchase';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

const PRINT_CAPABILITIES = JSON.parse(readFileSync(resolve(__dirname, '../../../../apis/vouchers/contracts/print-capabilities-v1.json'), 'utf8'));
const COMPANY = '01990000-0000-7000-8000-00000000000c';
const TEMPLATE = '01990000-0000-7000-8000-000000000001';
const VERSION = '01990000-0000-7000-8000-000000000002';
const page = { limit: 200, has_more: false, next_cursor: null };

function answers(kind: string | null = 'PURCHASE') {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    if (path.endsWith(`/versions/${VERSION}`)) {
      return { id: VERSION, template_id: TEMPLATE, version_number: 1, schema_version: '1.1.0', layout_definition: layoutToWire(standardPurchaseLayout('ITEMS')), created_at: '2026-11-04T00:00:00Z' } as never;
    }
    if (path.endsWith('/versions')) {
      return { items: [{ id: VERSION, template_id: TEMPLATE, version_number: 1, schema_version: '1.1.0', created_at: '2026-11-04T00:00:00Z' }], page } as never;
    }
    if (path.endsWith(`/templates/${TEMPLATE}`)) {
      return { id: TEMPLATE, company_id: COMPANY, code: 'our', name: 'Our purchase bill', paper_size: 'A4', page_orientation: 'PORTRAIT', status: 'DRAFT', is_system: false, current_version_id: null, voucher_kind: kind, line_profile: kind ? 'ITEMS' : null } as never;
    }
    if (path.endsWith('/assignments')) return { items: [], page } as never;
    if (path.endsWith('/assets')) return { items: [] } as never;
    if (path.endsWith('/print-capabilities')) return PRINT_CAPABILITIES as never;
    if (path.endsWith('/vouchers')) return { items: [], page: { ...page, limit: 25 } } as never;
    if (path.endsWith('/voucher-types')) return { items: [], page } as never;
    throw new Error('unexpected ' + request.path);
  };
}

function mount(access: Partial<{ routing: boolean; manageRouting: boolean; preview: boolean }> = {}) {
  const { routing = true, manageRouting = true, preview = true } = access;
  return render(
    <PermissionProvider permissions={['design.template.read', 'design.template.manage']}>
      <DesignerRoute company={COMPANY} templateId={TEMPLATE} canManage canReadRouting={routing} canManageRouting={manageRouting} canReadVouchers canPreview={preview} />
    </PermissionProvider>,
  );
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
});

describe('the designer route, for a Purchase design', () => {
  it('opens a design started from the standard layout with nothing to fix', async () => {
    vi.mocked(serviceCall).mockImplementation(answers());
    mount();
    await screen.findAllByText(/Our purchase bill/);
    await waitFor(() => expect(screen.getByTestId('usage-empty')).toBeInTheDocument());
    expect(screen.queryByTestId('warnings')).toBeNull();
  });

  it('shows where it is used and offers the bill preview to someone who may use both', async () => {
    vi.mocked(serviceCall).mockImplementation(answers());
    const user = userEvent.setup();
    mount();
    expect(await screen.findByTestId('usage-empty')).toHaveTextContent('Not used for any voucher yet — the standard layout prints.');
    expect(screen.getByRole('button', { name: 'Use for a Purchase type…' })).toBeInTheDocument();
    const assignments = vi.mocked(serviceCall).mock.calls.map(([, request]) => request.path).filter((path) => path.includes('template_id='));
    expect(assignments).toEqual([`/v1/companies/${COMPANY}/assignments?template_id=${TEMPLATE}&limit=200`]);

    await user.click(screen.getByRole('button', { name: 'Preview with a saved bill' }));
    const dialog = await screen.findByRole('dialog', { name: 'Preview version 1 with a saved bill' });
    expect(await within(dialog).findByText('No saved Purchase bills match')).toBeInTheDocument();
  });

  it('offers neither without the rights for them', async () => {
    vi.mocked(serviceCall).mockImplementation(answers());
    mount({ routing: false, preview: false });
    await screen.findAllByText(/Our purchase bill/);
    expect(screen.queryByText('Used for')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Preview with a saved bill' })).toBeNull();
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.path.includes('template_id='))).toBe(false);
  });

  it('lists without assigning for a reader of routing who cannot manage it', async () => {
    vi.mocked(serviceCall).mockImplementation(answers());
    mount({ manageRouting: false });
    await screen.findByTestId('usage-empty');
    expect(screen.queryByRole('button', { name: 'Use for a Purchase type…' })).toBeNull();
  });

  it('offers both on a design for any voucher', async () => {
    vi.mocked(serviceCall).mockImplementation(answers(null));
    mount();
    await screen.findByTestId('usage-empty');
    expect(screen.getByRole('button', { name: 'Preview with a saved bill' })).toBeInTheDocument();
  });
});

describe('the designer route, for a kind that cannot print from a design yet', () => {
  it('keeps its message and offers neither', async () => {
    vi.mocked(serviceCall).mockImplementation(answers('SALES'));
    mount();
    expect(await screen.findByText(/Sales vouchers cannot be printed from a design yet/)).toBeInTheDocument();
    expect(screen.queryByText('Used for')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Preview with a saved bill' })).toBeNull();
  });
});

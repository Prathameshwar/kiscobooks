/**
 * Document routing — page structure.
 *
 * The page once put its headings, fields and notices straight into a `Card`, which has no padding
 * of its own: everything sat hard against the card's edge, the five-field form wrapped four-and-one,
 * and the rules table was a bare `<table>` outside the shared list surface. jsdom cannot judge
 * pixels, so these pin the wrappers the stylesheet's spacing depends on — a field that drifts back
 * outside a `CardBody` is the same defect again.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { DocumentRouting } from '../app/components/DocumentRouting';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const LIVE = '01990000-0000-7000-8000-000000000001';
const RULE = '01990000-0000-7000-8000-000000000003';
const page = { limit: 200, has_more: false, next_cursor: null };

const template = {
  id: LIVE,
  company_id: COMPANY,
  code: 'gst-invoice',
  name: 'GST tax invoice',
  paper_size: 'A4',
  page_orientation: 'PORTRAIT',
  status: 'PUBLISHED',
  is_system: false,
  current_version_id: '01990000-0000-7000-8000-00000000000a',
  updated_at: '2026-10-27T00:00:00Z',
};

const rule = {
  id: RULE,
  company_id: COMPANY,
  voucher_kind: 'SALES',
  template_id: LIVE,
  priority: 100,
  is_active: true,
  created_at: '2026-10-27T00:00:00Z',
};

const resolved = {
  template_id: LIVE,
  template_code: 'gst-invoice',
  template_name: 'GST tax invoice',
  version_id: '01990000-0000-7000-8000-00000000000a',
  version_number: 3,
  layout_digest: 'ab'.repeat(32),
  layout_definition: { schema_version: '1.1.0' },
  assignment_rule_id: RULE,
};

function answer(options: { rules?: unknown[] } = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    if (path.endsWith('/assignments') && (request.method ?? 'GET') === 'GET') {
      return { items: options.rules ?? [rule], page } as never;
    }
    if (path.endsWith('/templates')) return { items: [template], page } as never;
    if (path.endsWith('/resolve')) return resolved as never;
    return rule as never;
  };
}

function mount(canManage = true) {
  return render(
    <PermissionProvider permissions={['design.assignment.read', 'design.assignment.manage']}>
      <DocumentRouting company={COMPANY} canManage={canManage} />
    </PermissionProvider>,
  );
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
});

describe('the page outline', () => {
  it('introduces each of its three jobs with a section heading under the page title', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    expect(screen.getByRole('heading', { level: 1, name: 'Document routing' })).toBeInTheDocument();
    for (const name of ['Rules in force', 'Add a rule', 'Check a document']) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument();
    }
  });

  it('tells a first-time reader they probably do not need it, before anything else', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    expect(
      screen.getByText(/Most companies never need this: every voucher already prints on the standard layout/),
    ).toBeInTheDocument();
  });

  it('leaves out the authoring section for a reader who may not manage routing', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount(false);
    await screen.findByRole('row', { name: /Sales/ });

    expect(screen.queryByRole('heading', { name: 'Add a rule' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Check a document' })).toBeInTheDocument();
  });
});

describe('the rules list', () => {
  it('is the shared table, with its own accessible name', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();

    const table = await screen.findByRole('table', { name: 'Routing rules' });
    expect(table.closest('.janso-table-shell')).not.toBeNull();
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(
      expect.arrayContaining(['Document', 'Template', 'Conditions', 'Priority', 'State']),
    );
  });

  it('lists the rules for a read-only reader without the empty state', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount(false);

    const row = await screen.findByRole('row', { name: /Sales/ });
    expect(within(row).getByText('Active')).toBeInTheDocument();
    expect(screen.queryByText('No routing rules yet')).not.toBeInTheDocument();
  });

  it('does not claim there are no rules while they are still loading', async () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    mount();

    expect(await screen.findByRole('table', { name: 'Routing rules' })).toBeInTheDocument();
    expect(screen.queryByText('No routing rules yet')).not.toBeInTheDocument();
  });

  it('says there are none, once it knows', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [] }));
    mount();

    expect(await screen.findByText('No routing rules yet')).toBeInTheDocument();
  });
});

describe('the forms', () => {
  it('keeps every field of the add form inside the card body, and its action in the footer', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    const body = screen.getByRole('combobox', { name: /Template/ }).closest('.janso-card__body');
    expect(body).not.toBeNull();
    for (const field of [
      screen.getAllByRole('combobox', { name: /Document kind/ })[0]!,
      screen.getByRole('combobox', { name: /Template/ }),
      screen.getByRole('textbox', { name: /Priority/ }),
      screen.getByRole('textbox', { name: /^Currency/ }),
      screen.getByRole('textbox', { name: /Customer tax category/ }),
    ]) {
      expect(body).toContainElement(field);
    }
    expect(screen.getByRole('button', { name: 'Add rule' }).closest('.janso-card__footer')).not.toBeNull();
  });

  it('lays both forms out on the same column template, so their edges line up', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    const add = screen.getByRole('combobox', { name: /Template/ }).closest('.janso-form-grid');
    const check = screen.getByRole('textbox', { name: /Document currency/ }).closest('.janso-form-grid');
    expect(add).toHaveClass('console-routing-fields');
    expect(check).toHaveClass('console-routing-fields');
  });

  it('puts the resolved answer inside the check card, above its Resolve action', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    await user.click(screen.getByRole('button', { name: 'Resolve' }));
    const result = await screen.findByText(/A matching rule routes this to GST tax invoice/);

    expect(result.closest('.janso-card__body')).not.toBeNull();
    expect(result.closest('.janso-card__footer')).toBeNull();
    expect(screen.getByRole('button', { name: 'Resolve' }).closest('.janso-card__footer')).not.toBeNull();
  });

  it('shows a refused write inside the add form, not floating beside the table', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') !== 'GET') {
        throw { status: 409, message: 'A rule for this document already exists.' };
      }
      return (await answer()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await user.selectOptions(await screen.findByRole('combobox', { name: /Template/ }), LIVE);
    await user.click(screen.getByRole('button', { name: 'Add rule' }));

    const failure = await screen.findByText(/already exists/);
    expect(failure.closest('.janso-card__body')).not.toBeNull();
  });
});

/**
 * Document routing — which layout each kind of document prints on.
 *
 * The missing half of the designer: a tenant could author a template and had no way to say when
 * it is used. Three things are worth testing here, and none of them is "the form submits":
 *
 *  - **Only a published template may be routed to.** A rule pointing at a draft resolves to
 *    nothing, which is a rule that silently does not work.
 *  - **Retired rules stay visible.** A rule is deactivated, not deleted, so hiding the retired
 *    ones makes "why is it still printing the old design?" unanswerable on the screen that owns
 *    the answer.
 *  - **Configured is not the same as defaulted.** `assignment_rule_id: null` means nothing
 *    matched and the company's most recently published template was used, and an operator reading
 *    "it resolves fine" needs to know which of those happened.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
const OTHER = '01990000-0000-7000-8000-00000000000d';
const LIVE = '01990000-0000-7000-8000-000000000001';
const DRAFT = '01990000-0000-7000-8000-000000000002';
const RULE = '01990000-0000-7000-8000-000000000003';
const page = { limit: 200, has_more: false, next_cursor: null };

function template(overrides: Record<string, unknown> = {}) {
  return {
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
    ...overrides,
  };
}

function rule(overrides: Record<string, unknown> = {}) {
  return {
    id: RULE,
    company_id: COMPANY,
    voucher_kind: 'SALES',
    template_id: LIVE,
    priority: 100,
    is_active: true,
    created_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

function responder(options: { rules?: unknown[]; templates?: unknown[]; resolved?: unknown } = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    if (path.endsWith('/assignments') && (request.method ?? 'GET') === 'GET') {
      return { items: options.rules ?? [rule()], page } as never;
    }
    if (path.endsWith('/templates')) {
      return { items: options.templates ?? [template()], page } as never;
    }
    if (path.endsWith('/resolve')) {
      return (options.resolved ?? {
        template_id: LIVE,
        template_code: 'gst-invoice',
        template_name: 'GST tax invoice',
        version_id: '01990000-0000-7000-8000-00000000000a',
        version_number: 3,
        layout_digest: 'ab'.repeat(32),
        layout_definition: { schema_version: '1.1.0' },
        assignment_rule_id: RULE,
      }) as never;
    }
    return rule() as never;
  };
}

const writes = () =>
  vi.mocked(serviceCall).mock.calls.filter(([, request]) => (request.method ?? 'GET') !== 'GET');

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

describe('the rules in force', () => {
  it('lists each rule against the template it routes to', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();

    const row = await screen.findByRole('row', { name: /Sales/ });
    expect(within(row).getByText('GST tax invoice')).toBeInTheDocument();
    expect(within(row).getByText('Active')).toBeInTheDocument();
    // No conditions means it is the default for that kind, which is worth saying out loud.
    expect(within(row).getByText('Any')).toBeInTheDocument();
  });

  it('asks for the retired ones too', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    const [[, request]] = vi.mocked(serviceCall).mock.calls;
    expect(request.service).toBe('design');
    expect(request.path).toContain('include_inactive=true');
  });

  it('shows a retired rule as retired, not as absent', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule({ is_active: false })] }),
    );
    mount();

    const row = await screen.findByRole('row', { name: /Sales/ });
    expect(within(row).getByText('Retired')).toBeInTheDocument();
    expect(within(row).getByRole('button', { name: 'Reinstate' })).toBeInTheDocument();
  });

  it('states the conditions a rule actually narrows on', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule({ currency_code: 'USD', customer_tax_category: 'export' })] }),
    );
    mount();

    const row = await screen.findByRole('row', { name: /Sales/ });
    expect(within(row).getByText(/Currency USD · Tax category export/)).toBeInTheDocument();
  });

  it('explains the fallback when nothing is configured', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    mount();

    expect(await screen.findByText('Without one, a document prints on the standard layout.')).toBeInTheDocument();
  });

  it('retires a rule by deactivating it, never by deleting it', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Retire' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.method).toBe('PATCH');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/assignments/${RULE}`);
    expect(request.body).toEqual({ is_active: false });
  });

  it('refuses a rule list carrying another company’s row', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule(), rule({ id: DRAFT, company_id: OTHER })] }),
    );
    mount();

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });
});

describe('adding a rule', () => {
  it('offers only templates that have something published', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        templates: [
          template(),
          template({ id: DRAFT, name: 'Half-built challan', status: 'DRAFT', current_version_id: null }),
        ],
      }),
    );
    mount();

    const select = await screen.findByRole('combobox', { name: /Template/ });
    expect(within(select).getByRole('option', { name: 'GST tax invoice' })).toBeInTheDocument();
    // A rule pointing at a draft resolves to nothing — a rule that silently does not work.
    expect(within(select).queryByRole('option', { name: 'Half-built challan' })).not.toBeInTheDocument();
  });

  it('says so when there is nothing publishable to route to', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ templates: [template({ status: 'DRAFT', current_version_id: null })] }),
    );
    mount();

    expect(await screen.findByText(/may only point at a template with a published version/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add rule' })).not.toBeInTheDocument();
  });

  it('sends the kind, the template and the priority, omitting blank conditions', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await user.selectOptions(await screen.findByRole('combobox', { name: /Template/ }), LIVE);
    await user.click(screen.getByRole('button', { name: 'Add rule' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.method).toBe('POST');
    expect(request.body).toEqual({ voucher_kind: 'SALES', template_id: LIVE, priority: 100 });
    // `""` is a 422 on a field nobody touched; absent and null are the same rule.
    expect(request.body).not.toHaveProperty('currency_code');
    expect(request.body).not.toHaveProperty('customer_tax_category');
  });

  it('upper-cases a currency the way the service expects it', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await user.selectOptions(await screen.findByRole('combobox', { name: /Template/ }), LIVE);
    await user.type(screen.getByRole('textbox', { name: /^Currency/ }), 'inr');
    await user.click(screen.getByRole('button', { name: 'Add rule' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect((writes()[0]![1].body as Record<string, unknown>).currency_code).toBe('INR');
  });

  it('puts a per-field rejection beside its own input', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') !== 'GET') {
        throw {
          status: 422,
          message: 'Validation failed',
          fields: { priority: 'Priority must be between 1 and 1000.' },
        };
      }
      return (await responder()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await user.selectOptions(await screen.findByRole('combobox', { name: /Template/ }), LIVE);
    await user.click(screen.getByRole('button', { name: 'Add rule' }));

    expect(await screen.findByText(/between 1 and 1000/)).toBeInTheDocument();
  });

  it('offers no form at all to a reader who may not manage routing', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount(false);

    await screen.findByRole('row', { name: /Sales/ });
    expect(screen.queryByRole('button', { name: 'Add rule' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retire' })).not.toBeInTheDocument();
  });
});

describe('checking what a document resolves to', () => {
  it('does not give two inputs on one screen the same accessible name', async () => {
    // A condition on a rule and a fact about a document are different questions; sharing a
    // label makes the screen unusable for anyone navigating by it.
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();
    await screen.findByRole('row', { name: /Sales/ });

    const names = screen
      .getAllByRole('textbox')
      .map((input) => input.getAttribute('aria-label') ?? (input as HTMLInputElement).labels?.[0]?.textContent ?? '');
    expect(new Set(names).size).toBe(names.length);
  });

  it('asks the same question the renderer will ask', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await screen.findByRole('row', { name: /Sales/ });
    await user.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.path).toBe(`/v1/companies/${COMPANY}/resolve`);
    expect(request.body).toEqual({ voucher_kind: 'SALES' });
    expect(await screen.findByText(/A matching rule routes this to GST tax invoice/)).toBeInTheDocument();
  });

  it('distinguishes a configured answer from a defaulted one', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        resolved: {
          template_id: LIVE,
          template_code: 'gst-invoice',
          template_name: 'GST tax invoice',
          version_id: '01990000-0000-7000-8000-00000000000a',
          version_number: 3,
          layout_digest: 'ab'.repeat(32),
          layout_definition: { schema_version: '1.1.0' },
          assignment_rule_id: null,
        },
      }),
    );
    const user = userEvent.setup();
    mount();

    await screen.findByRole('row', { name: /Sales/ });
    await user.click(screen.getByRole('button', { name: 'Resolve' }));

    // The distinction an operator needs: nothing matched, and it worked anyway. Which template the
    // service reached for is the most recently published one — not "the only one", which would be
    // untrue the day there are two.
    expect(await screen.findByText(/No rule matched/)).toBeInTheDocument();
    expect(screen.getByText(/the company’s most recently published template/)).toBeInTheDocument();
    expect(screen.queryByText(/only published template/)).not.toBeInTheDocument();
  });

  it('reports a document with nothing to print on as a failure, not as silence', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (request.path.endsWith('/resolve')) {
        throw { status: 404, message: 'No published template resolves for this document.' };
      }
      return (await responder()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await screen.findByRole('row', { name: /Sales/ });
    await user.click(screen.getByRole('button', { name: 'Resolve' }));

    expect(await screen.findByText(/No published template resolves/)).toBeInTheDocument();
  });
});

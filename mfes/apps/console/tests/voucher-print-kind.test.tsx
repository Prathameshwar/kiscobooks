/**
 * One voucher kind's print page.
 *
 * Nobody has to set anything up: a voucher prints on the standard layout until its company makes a
 * layout of its own. What can go quietly wrong is the page *claiming* something else:
 *
 *  - **"Custom layout" that is not printing.** A rule on a template with no published version is
 *    skipped when a document resolves, so a draft in progress must read as the standard layout
 *    still in use — and a retired rule, or one with conditions, is not the kind's layout at all.
 *  - **Customize must leave one thing behind, not two.** It makes a template *and* the kind's
 *    default rule. If the rule cannot be written the template exists regardless, so the person is
 *    offered it rather than a form that would only collide on the code.
 *  - **Offers the service will refuse.** One active rule per exact set of conditions *for a
 *    company*, whichever template it names — so the picker is offered only while the company has no
 *    default of its own. A default set for the whole organisation is somebody else's to change and
 *    must not block the company from having its own.
 *  - **Authority is read piece by piece.** A reader sees the page without the buttons; a template
 *    author without routing access still gets a way to start one; nobody gets a control for a
 *    write they cannot make.
 *  - **The table must be this kind's.** Asked of the service by `voucher_kind`, and a row of another
 *    kind in the answer is refused rather than shown under the wrong heading.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { VoucherPrintKind } from '../app/components/VoucherPrintKind';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const TENANT_WIDE = '00000000-0000-0000-0000-000000000000';
const GST = '01990000-0000-7000-8000-000000000001';
const THERMAL = '01990000-0000-7000-8000-000000000002';
const DRAFT = '01990000-0000-7000-8000-000000000003';
const GONE = '01990000-0000-7000-8000-000000000004';
const RULE = '01990000-0000-7000-8000-0000000000a1';
const OLD_RULE = '01990000-0000-7000-8000-0000000000a2';
const FRESH = '01990000-0000-7000-8000-000000000007';
const FIRST_PAGE = { limit: 200, has_more: false, next_cursor: null };
const MORE = { limit: 200, has_more: true, next_cursor: 'next' };
const ADVANCED = 'Advanced: other templates and rules';

function template(overrides: Record<string, unknown> = {}) {
  return {
    id: GST,
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

const thermal = () => template({ id: THERMAL, code: 'thermal', name: 'Thermal receipt' });
const draft = () =>
  template({ id: DRAFT, code: 'half', name: 'Half-built challan', status: 'DRAFT', current_version_id: null });

function rule(overrides: Record<string, unknown> = {}) {
  return {
    id: RULE,
    company_id: COMPANY,
    voucher_kind: 'SALES',
    template_id: GST,
    priority: 100,
    is_active: true,
    created_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

type Answers = {
  rules?: unknown[];
  templates?: unknown[];
  rulesPage?: unknown;
  templatesPage?: unknown;
  /** Refuse the write that makes a template the kind's layout. */
  assignmentRefusal?: { status: number; message: string; fields?: Record<string, string> };
};

function responder(options: Answers = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    const method = request.method ?? 'GET';
    if (path.endsWith('/assignments') && method === 'GET') {
      return { items: options.rules ?? [rule()], page: options.rulesPage ?? FIRST_PAGE } as never;
    }
    if (path.endsWith('/assignments') && method === 'POST' && options.assignmentRefusal) throw options.assignmentRefusal;
    if (path.endsWith('/templates') && method === 'GET') {
      return { items: options.templates ?? [template()], page: options.templatesPage ?? FIRST_PAGE } as never;
    }
    if (path.endsWith('/templates')) return { id: FRESH, company_id: COMPANY } as never;
    return rule() as never;
  };
}

const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => (request.method ?? 'GET') !== 'GET');
const reads = (suffix: string) =>
  vi.mocked(serviceCall).mock.calls.filter(
    ([, request]) => (request.method ?? 'GET') === 'GET' && request.path.split('?')[0]!.endsWith(suffix),
  );

function mount(access: { templates?: boolean; read?: boolean; routing?: boolean } = {}, kind = 'SALES') {
  const { templates = true, read = true, routing = true } = access;
  return render(
    <PermissionProvider permissions={['design.template.read']}>
      <VoucherPrintKind
        company={COMPANY}
        kind={kind}
        canManageTemplates={templates}
        canReadRouting={read}
        canManageRouting={routing}
      />
    </PermissionProvider>,
  );
}

/** The layout card: what the voucher prints on, as a person reads it. */
const layoutHeading = (name: string | RegExp) => screen.findByRole('heading', { level: 3, name });
/** Opens the collapsed Advanced section, as a person would, and returns it. */
async function openAdvanced(user: ReturnType<typeof userEvent.setup>) {
  const summary = await screen.findByText(ADVANCED);
  await user.click(summary);
  return summary.closest('details')!;
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(goTo).mockReset();
});

describe('the page', () => {
  it('names the voucher and says it prints on the standard layout unless customized', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();

    expect(await screen.findByRole('heading', { level: 1, name: 'Sales print' })).toBeInTheDocument();
    expect(
      screen.getByText(/Invoice, cash or credit sale\. It prints on the standard layout unless a layout has been set for it/),
    ).toBeInTheDocument();
  });

  it('can be left for the card list, the gallery, and the voucher type', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();
    await layoutHeading('GST tax invoice');

    expect(screen.getByRole('link', { name: 'Back to voucher print' })).toHaveAttribute('href', '/documents/vouchers');
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(crumbs).getByRole('link', { name: 'Print templates' })).toHaveAttribute('href', '/invoice-designer');
    expect(within(crumbs).getByRole('link', { name: 'Voucher print' })).toHaveAttribute('href', '/documents/vouchers');
    expect(screen.getByRole('link', { name: 'Manage voucher type' })).toHaveAttribute('href', '/masters/voucher-types');
  });

  it('uses the short name of any kind in its title', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    mount({}, 'CREDIT_NOTE');

    expect(await screen.findByRole('heading', { level: 1, name: 'Credit note print' })).toBeInTheDocument();
    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.getByText('Every credit note document prints on the standard layout.', { exact: false })).toBeInTheDocument();
  });

  it('says what it is doing while it finds out, rather than guessing the standard layout', async () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    mount();

    expect(await screen.findByText('Checking which layout sales prints on…')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
  });
});

describe('what it prints on', () => {
  it('is the standard layout until the company makes one of its own — and nothing is asked of anyone', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.getByText('Built in')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize layout' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Back to standard layout/ })).not.toBeInTheDocument();
  });

  it('is the company’s own template once its default rule is in force and the template is published', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();

    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
    expect(screen.getByText('Custom layout')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit design' })).toHaveAttribute('href', `/invoice-designer/${GST}`);
    expect(screen.getByRole('button', { name: 'Back to standard layout' })).toBeInTheDocument();
    // There is already a layout to edit; offering to make another here would only be refused.
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
  });

  it('lets a reader look at the design without offering to change it', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount({ templates: false, routing: false });

    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View design' })).toHaveAttribute('href', `/invoice-designer/${GST}`);
    expect(screen.queryByRole('link', { name: 'Edit design' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Back to standard layout/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
  });

  it('is still the standard layout while the template is a draft — a draft is skipped when a document resolves', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ template_id: DRAFT })], templates: [draft()] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.getByText('Draft in progress')).toBeInTheDocument();
    expect(
      screen.getByText('Half-built challan is still a draft. Sales documents keep printing on the standard layout until it is published.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Continue designing' })).toHaveAttribute('href', `/invoice-designer/${DRAFT}`);
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it('is not a custom layout because of a rule that was retired', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ is_active: false })] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it.each([
    ['a currency', { currency_code: 'USD' }],
    ['a tax category', { customer_tax_category: 'B2B' }],
    ['a voucher type', { voucher_type_id: '01990000-0000-7000-8000-0000000000e1' }],
    ['a branch', { branch_id: '01990000-0000-7000-8000-0000000000e2' }],
  ])('is not the kind’s layout when the rule is for %s only', async (_what, conditions) => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule(conditions)] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize layout' })).toBeInTheDocument();
  });

  it('shows a layout set for the whole organisation as such, and still lets the company have its own', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: TENANT_WIDE })] }));
    mount();

    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
    expect(screen.getByText('Organisation layout')).toBeInTheDocument();
    expect(screen.getByText(/set for your whole organisation/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize layout' })).toBeInTheDocument();
    // Retiring it needs a tenant-level grant the console cannot tell this actor has.
    expect(screen.queryByRole('button', { name: /Back to standard layout/ })).not.toBeInTheDocument();
  });

  it('prefers the company’s own default to one set for the whole organisation', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [
          rule({ id: OLD_RULE, company_id: TENANT_WIDE, template_id: THERMAL, created_at: '2026-10-26T00:00:00Z' }),
          rule(),
        ],
        templates: [template(), thermal()],
      }),
    );
    mount();

    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
    expect(screen.getByText('Custom layout')).toBeInTheDocument();
    expect(screen.queryByText('Organisation layout')).not.toBeInTheDocument();
  });

  it('says a layout exists but cannot be shown, rather than calling it standard, when its template is not in the list', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ template_id: GONE })], templates: [template()] }));
    mount();

    expect(await layoutHeading('Custom layout')).toBeInTheDocument();
    expect(screen.getByText(/its template cannot be shown here/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /design|Continue designing/ })).not.toBeInTheDocument();
    // Retiring is always safe, so a layout nobody can show is still one somebody can end.
    expect(screen.getByRole('button', { name: 'Back to standard layout' })).toBeInTheDocument();
  });

  it('claims nothing when either list runs past one page, and points to Document routing', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [], rulesPage: MORE }));
    mount();

    expect(await screen.findByText(/more rules or templates than fit on one page/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Document routing' })).toHaveAttribute('href', '/documents/routing');
  });

  it('claims nothing when the template list runs past one page, either', async () => {
    // A rule whose template fell off the page would read as an unknown template, or as no layout at all.
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [], templatesPage: MORE }));
    mount();

    expect(await screen.findByText(/more rules or templates than fit on one page/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
  });

  it('shows a refusal as a refusal, not as the standard layout', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'You may not read templates here.' });
    mount();

    expect(await screen.findByText('You may not read templates here.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
  });

  it('refuses a list carrying a row of another kind', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule(), rule({ id: OLD_RULE, voucher_kind: 'PURCHASE' })] }));
    mount();

    expect(await screen.findByText(/could not be verified/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();
  });

  it('refuses a list carrying another company’s row', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: OTHER })] }));
    mount();

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });

  it('asks the service for this kind only, retired rules included', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount({}, 'RECEIPT');
    await screen.findByRole('heading', { name: 'Receipt print' });
    await waitFor(() => expect(reads('/assignments')).toHaveLength(1));

    const [[, request]] = reads('/assignments');
    expect(request.service).toBe('design');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/assignments?include_inactive=true&limit=200&voucher_kind=RECEIPT`);
  });
});

describe('customizing', () => {
  async function customize(user: ReturnType<typeof userEvent.setup>, name = 'Sales challan', code = 'sales-challan') {
    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), name);
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), code);
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    return dialog;
  }

  it('says what will happen: it opens empty in the designer, and the standard layout prints until it is published', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));

    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    expect(
      within(dialog).getByText(
        'It opens in the designer on an empty page. Once you publish it, it becomes the layout for sales; until then sales documents keep printing on the standard layout.',
      ),
    ).toBeInTheDocument();
  });

  it('makes the template and, in the same step, the kind’s default rule on it — then opens the designer', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    const user = userEvent.setup();
    mount();

    await customize(user);

    await waitFor(() => expect(writes()).toHaveLength(2));
    const [[, created], [, routed]] = writes();
    expect(created.method).toBe('POST');
    expect(created.path).toBe(`/v1/companies/${COMPANY}/templates`);
    expect(created.body).not.toHaveProperty('initial_canvas');
    // The rule names the template that was just made, for this kind, with no conditions.
    expect(routed.method).toBe('POST');
    expect(routed.path).toBe(`/v1/companies/${COMPANY}/assignments`);
    expect(routed.body).toEqual({ voucher_kind: 'SALES', template_id: FRESH, priority: 100 });
    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
  });

  it('keeps the template and offers it when the rule cannot be written — a second try would only collide on the code', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [], assignmentRefusal: { status: 409, message: 'an active rule already matches exactly these criteria' } }),
    );
    const user = userEvent.setup();
    mount();

    const dialog = await customize(user);

    expect(
      await within(dialog).findByText(
        'The template was created. It could not be made the layout for sales. Open it, publish it, then choose it under Advanced on this page.',
      ),
    ).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    // The form is gone, so nothing invites a second create.
    expect(within(dialog).queryByRole('textbox', { name: /Name/ })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /Create and open/ })).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: 'Open the template' }));

    expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH);
    expect(writes().filter(([, request]) => request.path.endsWith('/templates'))).toHaveLength(1);
  });

  it('can be put off after the rule fails, leaving the page where it was', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [], assignmentRefusal: { status: 409, message: 'an active rule already matches exactly these criteria' } }),
    );
    const user = userEvent.setup();
    mount();

    const dialog = await customize(user);
    await user.click(await within(dialog).findByRole('button', { name: 'Not now' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(goTo).not.toHaveBeenCalled();
  });

  it('does not make a second template while the rule is still being written', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST' && request.path.endsWith('/assignments')) return new Promise<never>(() => undefined);
      return (await responder({ rules: [] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    const dialog = await customize(user);

    // The template exists and the rule is in flight: the form's own request is long over, so only the
    // follow-up keeps the button from making a second template.
    await waitFor(() => expect(writes()).toHaveLength(2));
    const busy = within(dialog).getByRole('button', { name: 'Creating…' });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(writes().filter(([, request]) => request.path.endsWith('/templates'))).toHaveLength(1);
  });

  it('puts a refusal of the template itself in the form, and writes no rule', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST' && request.path.endsWith('/templates')) {
        throw { status: 409, message: "template code 'sales-challan' is already in use" };
      }
      return (await responder({ rules: [] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    const dialog = await customize(user);

    expect(await within(dialog).findByText("template code 'sales-challan' is already in use")).toBeInTheDocument();
    expect(writes()).toHaveLength(1);
    expect(goTo).not.toHaveBeenCalled();
  });

  it('can be started again from the organisation’s layout, which does not stand in its way', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: TENANT_WIDE })] }));
    const user = userEvent.setup();
    mount();

    await customize(user);

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]![1].body).toEqual({ voucher_kind: 'SALES', template_id: FRESH, priority: 100 });
  });
});

describe('going back to the standard layout', () => {
  it('asks first, saying what stops and what is kept', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Back to standard layout' }));

    const dialog = await screen.findByRole('dialog', { name: 'Go back to the standard layout for sales?' });
    expect(within(dialog).getByText(/GST tax invoice stops being used for sales/)).toBeInTheDocument();
    expect(within(dialog).getByText(/kept in Print templates, and you can use it again later/)).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('retires the rule, and reads the page again so the standard layout is what it then shows', async () => {
    let retired = false;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'PATCH') {
        retired = true;
        return rule({ is_active: false }) as never;
      }
      return (await responder({ rules: [rule({ is_active: !retired })] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Back to standard layout' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Back to standard layout' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.method).toBe('PATCH');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/assignments/${RULE}`);
    expect(request.body).toEqual({ is_active: false });
    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize layout' })).toBeInTheDocument();
  });

  it('writes nothing when it is called off', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Back to standard layout' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(writes()).toHaveLength(0);
    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
  });

  it('keeps the question open and says why when it fails — once, not behind the dialog as well', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'PATCH') throw { status: 409, message: 'That rule changed. Reload and try again.' };
      return (await responder()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Back to standard layout' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Back to standard layout' }));

    expect(await within(dialog).findByText('That rule changed. Reload and try again.')).toBeInTheDocument();
    expect(screen.getAllByText('That rule changed. Reload and try again.')).toHaveLength(1);
    // Cancelling clears it, so the next attempt does not start with yesterday’s refusal.
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('That rule changed. Reload and try again.')).not.toBeInTheDocument();
  });

  it('calls it stopping, not going back, while the template is only a draft — and does the same thing', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ template_id: DRAFT })], templates: [draft()] }));
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Stop customizing' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Stop customizing' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]![1].body).toEqual({ is_active: false });
  });

  it('is not offered without the grant to change a rule', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount({ routing: false });

    await layoutHeading('GST tax invoice');
    expect(screen.queryByRole('button', { name: /Back to standard layout/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit design' })).toBeInTheDocument();
  });
});

describe('the rules, under Advanced', () => {
  it('are out of the way until asked for', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();

    const summary = await screen.findByText(ADVANCED);
    expect(summary.closest('details')).not.toHaveAttribute('open');
    await userEvent.click(summary);
    expect(await screen.findByRole('row', { name: /GST tax invoice/ })).toBeVisible();
  });

  it('lists each rule against the template it routes to, linked to the designer', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ currency_code: 'USD' })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const row = await screen.findByRole('row', { name: /GST tax invoice/ });
    expect(within(row).getByRole('link', { name: 'GST tax invoice' })).toHaveAttribute('href', `/invoice-designer/${GST}`);
    expect(within(row).getByText('gst-invoice')).toBeInTheDocument();
    expect(within(row).getByText('Currency USD')).toBeInTheDocument();
    expect(within(row).getByText('Active')).toBeInTheDocument();
  });

  it('says when a rule is scoped to a voucher type or a branch, so it is not read as the default', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [
          rule({ voucher_type_id: '01990000-0000-7000-8000-0000000000e1' }),
          rule({ id: OLD_RULE, branch_id: '01990000-0000-7000-8000-0000000000e2', priority: 50 }),
        ],
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByText('Specific voucher type')).toBeInTheDocument();
    expect(screen.getByText('Specific branch')).toBeInTheDocument();
    expect(screen.queryByText('Any')).not.toBeInTheDocument();
  });

  it('puts the rules in force first, highest priority leading, and keeps the retired ones', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [
          rule({ id: OLD_RULE, template_id: THERMAL, is_active: false, priority: 900 }),
          rule({ id: RULE, priority: 100, currency_code: 'USD' }),
          rule({ id: '01990000-0000-7000-8000-0000000000a3', template_id: THERMAL, priority: 500, currency_code: 'EUR' }),
        ],
        templates: [template(), thermal()],
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await screen.findAllByRole('row', { name: /Thermal receipt/ });
    const names = screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[0]!.textContent);
    // Resolution order: what is in force and wins comes first; a retired rule is kept, last.
    expect(names).toEqual(['Thermal receipt', 'GST tax invoice', 'Thermal receipt']);
    const retired = screen.getAllByRole('row').at(-1)!;
    expect(within(retired).getByText('Retired')).toBeInTheDocument();
    expect(within(retired).getByRole('button', { name: 'Reinstate Thermal receipt' })).toBeInTheDocument();
  });

  it('says there are none, and that the standard layout prints, when nothing is routed to this kind', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByText('No rules for sales')).toBeInTheDocument();
    expect(screen.getByText('Sales documents print on the standard layout.')).toBeInTheDocument();
  });

  it('names each retire button for the template it acts on', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [rule(), rule({ id: OLD_RULE, template_id: THERMAL, priority: 50, currency_code: 'USD' })],
        templates: [template(), thermal()],
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Retire GST tax invoice' })).toBeInTheDocument();
    // A rule with conditions says so in its name, so two rules on one template are told apart.
    expect(screen.getByRole('button', { name: 'Retire Thermal receipt, Currency USD' })).toBeInTheDocument();
  });

  it('retires one rule by deactivating it, and reloads', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ currency_code: 'USD' })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await user.click(await screen.findByRole('button', { name: 'Retire GST tax invoice, Currency USD' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.method).toBe('PATCH');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/assignments/${RULE}`);
    expect(request.body).toEqual({ is_active: false });
    await waitFor(() => expect(reads('/assignments')).toHaveLength(2));
  });

  it('reports a failed retire where it can be seen', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'PATCH') throw { status: 409, message: 'That rule changed. Reload and try again.' };
      return (await responder({ rules: [rule({ currency_code: 'USD' })] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await user.click(await screen.findByRole('button', { name: 'Retire GST tax invoice, Currency USD' }));

    expect(await screen.findByText('That rule changed. Reload and try again.')).toBeInTheDocument();
  });

  it('offers nothing on a rule whose template is gone — it was retired because the template was archived', async () => {
    // The service deactivates a template's rules when it archives it, and the list leaves archived
    // templates out. Reinstating one would leave an active rule that resolves nothing.
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule({ id: OLD_RULE, template_id: GONE, is_active: false })], templates: [template()] }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const row = await screen.findByRole('row', { name: /Unknown template/ });
    expect(within(row).getByText('Retired')).toBeInTheDocument();
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
    expect(within(row).queryByRole('link')).not.toBeInTheDocument();
  });

  it('offers nothing on a tenant-wide rule, which needs a tenant-level grant', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: TENANT_WIDE })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const row = await screen.findByRole('row', { name: /GST tax invoice/ });
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('using a template that already exists, under Advanced', () => {
  it('offers every published template, and no draft', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [], templates: [template(), thermal(), draft()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const select = await screen.findByRole('combobox', { name: 'Template' });
    expect(within(select).getByRole('option', { name: 'GST tax invoice' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'Thermal receipt' })).toBeInTheDocument();
    // A draft is skipped when a document resolves, so it is not a choice.
    expect(within(select).queryByRole('option', { name: 'Half-built challan' })).not.toBeInTheDocument();
  });

  it('still offers a template that only has a conditioned rule — a different rule, so no conflict', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ currency_code: 'USD' })], templates: [template(), thermal()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const select = await screen.findByRole('combobox', { name: 'Template' });
    expect(within(select).getByRole('option', { name: 'GST tax invoice' })).toBeInTheDocument();
  });

  it('offers a template whose only default has been retired', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ is_active: false })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const select = await screen.findByRole('combobox', { name: 'Template' });
    expect(within(select).getByRole('option', { name: 'GST tax invoice' })).toBeInTheDocument();
  });

  it('is also offered where the organisation sets the layout, since the company’s own rule does not collide with it', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: TENANT_WIDE })], templates: [template(), thermal()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('combobox', { name: 'Template' })).toBeInTheDocument();
  });

  it('offers no picker while the company has its own layout, since the service would refuse a second', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ templates: [template(), thermal()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(
      await screen.findByText('To use a different template for sales, go back to the standard layout first, then choose it here.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use for sales' })).not.toBeInTheDocument();
  });

  it('brings the picker back once the company is back on the standard layout', async () => {
    let retired = false;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'PATCH') {
        retired = true;
        return rule({ is_active: false }) as never;
      }
      return (await responder({ rules: [rule({ is_active: !retired })], templates: [template(), thermal()] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Back to standard layout' }));
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Back to standard layout' }));
    await openAdvanced(user);

    expect(await screen.findByRole('combobox', { name: 'Template' })).toBeInTheDocument();
  });

  it('routes the kind to the chosen template at the default priority, with no conditions', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [], templates: [template(), thermal()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const use = await screen.findByRole('button', { name: 'Use for sales' });
    expect(use).toBeDisabled();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Template' }), THERMAL);
    await user.click(use);

    await waitFor(() => expect(writes()).toHaveLength(1));
    const [[, request]] = writes();
    expect(request.method).toBe('POST');
    expect(request.path).toBe(`/v1/companies/${COMPANY}/assignments`);
    expect(request.body).toEqual({ voucher_kind: 'SALES', template_id: THERMAL, priority: 100 });
    // The page is read again, so the new layout is on it rather than assumed to be.
    await waitFor(() => expect(reads('/assignments')).toHaveLength(2));
  });

  it('puts a rejection on the page', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [],
        templates: [template(), thermal()],
        assignmentRefusal: { status: 422, message: 'Validation failed', fields: { template_id: 'That template has no published version.' } },
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Template' }), THERMAL);
    await user.click(screen.getByRole('button', { name: 'Use for sales' }));

    expect(await screen.findByText('That template has no published version.')).toBeInTheDocument();
  });

  it('says there is nothing to choose when no template is published', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [], templates: [draft()] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByText(/No published template to choose from yet/)).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Template' })).not.toBeInTheDocument();
  });

  it('points to Document routing for conditions', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const section = (await screen.findByRole('heading', { name: 'Use an existing template' })).closest('header')!;
    expect(within(section).getByRole('link', { name: 'Document routing' })).toHaveAttribute('href', '/documents/routing');
  });
});

describe('what each level of access sees', () => {
  it('gives a reader the page and nothing that writes', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount({ templates: false, routing: false });
    await layoutHeading('GST tax invoice');
    await openAdvanced(user);

    await screen.findByRole('row', { name: /GST tax invoice/ });
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Retire/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Use an existing template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // The voucher type is somewhere to go, not something to change from here.
    expect(screen.getByRole('link', { name: 'Manage voucher type' })).toBeInTheDocument();
  });

  it('lets a template author start a template without routing access, and never asks for the rules', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount({ templates: true, read: false, routing: false });

    await user.click(await screen.findByRole('button', { name: 'New template' }));
    const dialog = await screen.findByRole('dialog', { name: 'New template' });
    expect(
      within(dialog).getByText('It opens in the designer on an empty page. A template is used for sales once someone with routing access chooses it.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Routing read access is required to see which layout sales prints on/)).toBeInTheDocument();
    expect(reads('/assignments')).toHaveLength(0);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
    expect(screen.queryByText(ADVANCED)).not.toBeInTheDocument();
  });

  it('starts only a template, never a rule, for an author who cannot route', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    const user = userEvent.setup();
    mount({ templates: true, read: true, routing: false });

    // They can see the standard layout is in use; the button says what it really does.
    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'New template' }));
    const dialog = await screen.findByRole('dialog', { name: 'New template' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));

    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
    expect(writes()).toHaveLength(1);
    expect(writes()[0]![1].path).toBe(`/v1/companies/${COMPANY}/templates`);
    expect(screen.queryByText(/Customize it to add your logo/)).not.toBeInTheDocument();
  });

  it('offers no way to choose a layout without read access, since the one in force is unknown', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount({ templates: true, read: false, routing: true });

    await screen.findByRole('button', { name: 'New template' });
    await waitFor(() => expect(reads('/templates')).toHaveLength(1));
    expect(screen.queryByRole('button', { name: 'Use for sales' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Back to standard layout/ })).not.toBeInTheDocument();
  });

  it('lets a router go back and choose without being able to design one', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ currency_code: 'USD' })], templates: [template(), thermal()] }));
    const user = userEvent.setup();
    mount({ templates: false, routing: true });
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Retire GST tax invoice, Currency USD' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Use for sales' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New template|Customize layout/ })).not.toBeInTheDocument();
  });
});

describe('what the service would resolve, not what was last written', () => {
  const ORG_RULE = '01990000-0000-7000-8000-0000000000b1';
  const ORG_TEMPLATE = '01990000-0000-7000-8000-000000000005';
  const orgTemplate = (overrides: Record<string, unknown> = {}) =>
    template({ id: ORG_TEMPLATE, company_id: TENANT_WIDE, code: 'house', name: 'House style', ...overrides });
  // Older than the company's own rules by default, so on equal priority the company's wins the tie.
  const orgRule = (overrides: Record<string, unknown> = {}) =>
    rule({ id: ORG_RULE, company_id: TENANT_WIDE, template_id: ORG_TEMPLATE, created_at: '2026-10-26T00:00:00Z', ...overrides });

  it('keeps saying the organisation’s layout prints while the company’s own is a draft — the draft is skipped', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [orgRule(), rule({ template_id: DRAFT })], templates: [orgTemplate(), draft()] }),
    );
    mount();

    expect(await layoutHeading('House style')).toBeInTheDocument();
    expect(screen.getByText('Organisation layout')).toBeInTheDocument();
    expect(screen.getByText(/This company’s own layout, Half-built challan, is still a draft\./)).toBeInTheDocument();
    // Not "standard layout … keeps printing", which is untrue while the organisation's layout prints.
    expect(screen.queryByText('Draft in progress')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3, name: 'Standard layout' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Continue designing' })).toHaveAttribute('href', `/invoice-designer/${DRAFT}`);
    expect(screen.getByRole('button', { name: 'Stop customizing' })).toBeInTheDocument();
  });

  it('says the organisation’s layout wins when it outranks the company’s own published one', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [orgRule({ priority: 300 }), rule()], templates: [orgTemplate(), template()] }),
    );
    mount();

    expect(await layoutHeading('House style')).toBeInTheDocument();
    expect(screen.getByText(/GST tax invoice, is not used while the organisation’s takes precedence/)).toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Customize layout' })).not.toBeInTheDocument();
  });

  it('says plainly what ending the company’s own layout leads to when the organisation has one', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [orgRule({ priority: 300 }), rule()], templates: [orgTemplate(), template()] }),
    );
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Remove this company’s layout' }));

    const dialog = await screen.findByRole('dialog', { name: 'Stop using GST tax invoice for sales?' });
    expect(within(dialog).getByText(/which then print on House style, set for your whole organisation/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/standard layout again/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Remove this company’s layout' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]![1].path).toBe(`/v1/companies/${COMPANY}/assignments/${RULE}`);
  });

  it('does not claim an organisation layout that is itself only a draft', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [orgRule()], templates: [orgTemplate({ status: 'DRAFT', current_version_id: null })] }),
    );
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.queryByText('Organisation layout')).not.toBeInTheDocument();
  });

  it('writes a new layout at the organisation’s priority, so that being newer is enough to win the tie', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [orgRule({ priority: 300 })], templates: [orgTemplate()] }));
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    // The note says what is printing now, not "the standard layout", which would be untrue here.
    expect(within(dialog).getByText(/until then sales documents keep printing on House style/)).toBeInTheDocument();
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]![1].body).toEqual({ voucher_kind: 'SALES', template_id: FRESH, priority: 300 });
  });

  it('never writes below the usual priority', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [orgRule({ priority: 20 })], templates: [orgTemplate()] }));
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]![1].body).toEqual({ voucher_kind: 'SALES', template_id: FRESH, priority: 100 });
  });

  it('says a rule for particular documents is not the standard layout for everything', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ currency_code: 'USD' })] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.getByText(/Documents that match a rule under Advanced print on that rule’s layout instead\./)).toBeInTheDocument();
  });

  it('says nothing about particular documents when there are none', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [] }));
    mount();

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
    expect(screen.queryByText(/Documents that match a rule/)).not.toBeInTheDocument();
  });

  it('orders the rules table as the service resolves: priority before how specific a rule is', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [
          rule({ id: OLD_RULE, priority: 100, currency_code: 'USD', customer_tax_category: 'B2B' }),
          rule({ id: RULE, priority: 200 }),
        ],
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await screen.findAllByRole('row', { name: /GST tax invoice/ });
    const conditions = screen.getAllByRole('row').slice(1).map((row) => within(row).getAllByRole('cell')[2]!.textContent);
    // A rule pinning two criteria still loses to a default of higher priority.
    expect(conditions).toEqual(['Any', 'Currency USD · Tax category B2B']);
  });
});

describe('reinstating', () => {
  it('is not offered while an identical rule is in force — the service would have refused to write the second', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [rule(), rule({ id: OLD_RULE, template_id: THERMAL, is_active: false })],
        templates: [template(), thermal()],
      }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    const row = await screen.findByRole('row', { name: /Thermal receipt/ });
    expect(within(row).getByText('Retired')).toBeInTheDocument();
    expect(within(row).queryByRole('button')).not.toBeInTheDocument();
  });

  it('is offered once nothing identical is in force', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ is_active: false })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Reinstate GST tax invoice' })).toBeInTheDocument();
  });

  it('is offered when what is in force has other conditions — a different rule', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule({ is_active: false }), rule({ id: OLD_RULE, currency_code: 'USD' })] }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Reinstate GST tax invoice' })).toBeInTheDocument();
  });

  it('is offered when the identical rule in force belongs to another company', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ is_active: false }), rule({ id: OLD_RULE, company_id: TENANT_WIDE })] }));
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Reinstate GST tax invoice' })).toBeInTheDocument();
  });
});

describe('telling rules apart', () => {
  it('names two rules on one template differently, so a screen reader can tell which it is acting on', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [rule(), rule({ id: OLD_RULE, priority: 50, currency_code: 'USD' })] }),
    );
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    expect(await screen.findByRole('button', { name: 'Retire GST tax invoice' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retire GST tax invoice, Currency USD' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Layout rules for sales' })).toBeInTheDocument();
  });
});

describe('writes that go wrong', () => {
  it('lets a retire go through after another write was left uncertain by a server error', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if ((request.method ?? 'GET') === 'POST') throw { status: 503, message: 'The design service did not answer.' };
      return (await responder({ rules: [rule({ currency_code: 'USD' })], templates: [template(), thermal()] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    await openAdvanced(user);

    await user.selectOptions(await screen.findByRole('combobox', { name: 'Template' }), THERMAL);
    await user.click(screen.getByRole('button', { name: 'Use for sales' }));
    expect(await screen.findByText('The design service did not answer.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retire GST tax invoice, Currency USD' }));

    await waitFor(() => expect(writes().filter(([, request]) => request.method === 'PATCH')).toHaveLength(1));
  });

  it('does not put a refusal of Customize’s rule under a picker nobody touched', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({
        rules: [],
        assignmentRefusal: { status: 422, message: 'Validation failed', fields: { template_id: 'That template has no published version.' } },
      }),
    );
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await user.click(await within(dialog).findByRole('button', { name: 'Not now' }));
    await openAdvanced(user);

    await screen.findByRole('combobox', { name: 'Template' });
    expect(screen.queryByText('That template has no published version.')).not.toBeInTheDocument();
  });

  it('reads the page again after Customize’s rule is refused, so a stale page shows what is really there', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [], assignmentRefusal: { status: 409, message: 'an active rule already matches exactly these criteria' } }),
    );
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));

    await within(dialog).findByText(/The template was created/);
    await waitFor(() => expect(reads('/assignments')).toHaveLength(2));
    expect(reads('/templates')).toHaveLength(2);
  });

  it('does not repeat a refusal behind the dialog that is already giving it', async () => {
    vi.mocked(serviceCall).mockImplementation(
      responder({ rules: [], assignmentRefusal: { status: 409, message: 'an active rule already matches exactly these criteria' } }),
    );
    const user = userEvent.setup();
    mount();

    await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
    const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Sales challan');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'sales-challan');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await within(dialog).findByText(/The template was created/);

    expect(screen.queryByText('an active rule already matches exactly these criteria')).not.toBeInTheDocument();
    // …but it is there once the dialog is put off, for a person who wants to know why.
    await user.click(within(dialog).getByRole('button', { name: 'Not now' }));
    expect(await screen.findByText('an active rule already matches exactly these criteria')).toBeInTheDocument();
  });

  it('says what failed, and offers another try, when the page cannot be read — it does not claim nothing changed', async () => {
    let asked = 0;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (request.path.split('?')[0]!.endsWith('/assignments') && (request.method ?? 'GET') === 'GET' && asked++ === 0) {
        throw { status: 500, message: 'The design service did not answer.' };
      }
      return (await responder({ rules: [] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();

    expect(await screen.findByText('The design service did not answer.')).toBeInTheDocument();
    expect(screen.queryByText(/Nothing was changed/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(await layoutHeading('Standard layout')).toBeInTheDocument();
  });
});

describe('who may look and who may change', () => {
  it('offers a reader only to look at a draft', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ template_id: DRAFT })], templates: [draft()] }));
    mount({ templates: false, routing: false });

    expect(await screen.findByText('Draft in progress')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View design' })).toHaveAttribute('href', `/invoice-designer/${DRAFT}`);
    expect(screen.queryByRole('link', { name: 'Continue designing' })).not.toBeInTheDocument();
  });

  it('offers only to look at a shipped template, which no company may change', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ templates: [template({ is_system: true })] }));
    mount();

    expect(await layoutHeading('GST tax invoice')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View design' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Edit design' })).not.toBeInTheDocument();
  });
});

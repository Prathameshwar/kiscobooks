/**
 * Plan R4 (2026-11-04): the designer says where a design is used and assigns it to a Purchase
 * type, without a trip to the routing page.
 *
 *  - **Only rules in force, only this design's.** Asked of the service by `template_id`; a row for
 *    another design, another company or a retired rule in the answer is refused, not shown.
 *  - **Plain words.** "Purchase · all types", "Purchase · Goods bill" — never an id.
 *  - **Authority piece by piece.** No routing read: no panel. Read without manage: a list and no
 *    buttons. No voucher read: rules still listed, only "all Purchase types" can be chosen.
 *  - **A duplicate is said plainly.** One active rule per criteria per company; the 409 names the
 *    vouchers and where to stop the other design.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { TemplateUsage, usageLabel } from '../app/(editor)/invoice-designer/TemplateUsage';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const TENANT_WIDE = '00000000-0000-0000-0000-000000000000';
const TEMPLATE = '01990000-0000-7000-8000-000000000001';
const ANOTHER_TEMPLATE = '01990000-0000-7000-8000-000000000002';
const GOODS = '01990000-0000-7000-8000-0000000000b1';
const SERVICES = '01990000-0000-7000-8000-0000000000b2';
const RETIRED_TYPE = '01990000-0000-7000-8000-0000000000b3';
const RULE = '01990000-0000-7000-8000-0000000000a1';
const TYPE_RULE = '01990000-0000-7000-8000-0000000000a2';
const PAGE = { limit: 200, has_more: false, next_cursor: null };

function rule(overrides: Record<string, unknown> = {}) {
  return {
    id: RULE,
    company_id: COMPANY,
    voucher_kind: 'PURCHASE',
    template_id: TEMPLATE,
    priority: 100,
    is_active: true,
    created_at: '2026-11-04T00:00:00Z',
    ...overrides,
  };
}
function type(id: string, name: string, status = 'ACTIVE') {
  return { id, company_id: COMPANY, kind: 'PURCHASE', name, code: name.toUpperCase().replace(/\W/g, '_'), status, row_version: 1 };
}

type Answers = {
  rules?: unknown[];
  rulesFailure?: { status: number; message: string };
  createFailure?: { status: number; message: string };
  stopFailure?: { status: number; message: string };
};
function responder(answers: Answers = {}) {
  let rules = answers.rules ?? [];
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    const method = request.method ?? 'GET';
    if (path.endsWith('/assignments') && method === 'GET') {
      if (answers.rulesFailure) throw answers.rulesFailure;
      return { items: rules, page: PAGE } as never;
    }
    if (path.endsWith('/voucher-types')) {
      return { items: [type(GOODS, 'Goods bill'), type(SERVICES, 'Service bill'), type(RETIRED_TYPE, 'Old bill', 'RETIRED')], page: PAGE } as never;
    }
    if (path.endsWith('/assignments') && method === 'POST') {
      if (answers.createFailure) throw answers.createFailure;
      const body = request.body as Record<string, unknown>;
      const created = rule({ id: TYPE_RULE, voucher_type_id: body.voucher_type_id ?? null });
      rules = [...rules, created];
      return created as never;
    }
    if (method === 'PATCH') {
      if (answers.stopFailure) throw answers.stopFailure;
      const id = path.split('/').at(-1);
      rules = (rules as { id: string }[]).filter((row) => row.id !== id);
      return rule({ id, is_active: false }) as never;
    }
    throw new Error('unexpected ' + method + ' ' + path);
  };
}

const calls = () => vi.mocked(serviceCall).mock.calls.map(([, request]) => request);
const writes = () => calls().filter((request) => (request.method ?? 'GET') !== 'GET');

function mount(access: { read?: boolean; manage?: boolean; types?: boolean; published?: boolean } = {}, onChanged = vi.fn()) {
  const { read = true, manage = true, types = true, published = true } = access;
  render(
    <TemplateUsage
      company={COMPANY}
      templateId={TEMPLATE}
      published={published}
      canRead={read}
      canManage={manage}
      canReadTypes={types}
      onChanged={onChanged}
    />,
  );
  return onChanged;
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
});

describe('where this design is used', () => {
  it('asks the service for this design’s rules in force, through the design boundary', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount();
    expect(await screen.findByTestId('usage-empty')).toHaveTextContent('Not used for any voucher yet — the standard layout prints.');
    const [read] = calls().filter((request) => request.path.includes('/assignments'));
    expect(read).toMatchObject({ service: 'design', path: `/v1/companies/${COMPANY}/assignments?template_id=${TEMPLATE}&limit=200` });
  });

  it('says it is checking while it reads', () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    mount();
    expect(screen.getByRole('status')).toHaveTextContent('Checking where this design is used…');
  });

  it('lists each rule in plain words, naming the Purchase type', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule(), rule({ id: TYPE_RULE, voucher_type_id: GOODS, currency_code: 'USD' })] }));
    mount();
    const list = await screen.findByRole('list', { name: 'Vouchers that print on this design' });
    await waitFor(() => expect(within(list).getByText('Purchase · Goods bill · currency USD')).toBeInTheDocument());
    expect(within(list).getByText('Purchase · all types')).toBeInTheDocument();
    expect(screen.queryByTestId('usage-unpublished')).toBeNull();
  });

  it('says the standard layout still prints while the design is not published', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule()] }));
    mount({ published: false });
    expect(await screen.findByTestId('usage-unpublished')).toHaveTextContent('keep printing on the standard layout until it is');
  });

  it('names a type it cannot read as a type, and does not ask for types without access', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ voucher_type_id: GOODS })] }));
    mount({ types: false });
    expect(await screen.findByText('Purchase · one voucher type')).toBeInTheDocument();
    expect(calls().some((request) => request.path.includes('/voucher-types'))).toBe(false);
  });

  it.each([
    ['another design’s rule', rule({ template_id: ANOTHER_TEMPLATE })],
    ['a retired rule', rule({ is_active: false })],
  ])('refuses an answer carrying %s', async (_, row) => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [row] }));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('Where this design is used could not be verified.');
  });

  it('refuses an answer carrying another company’s rule', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: OTHER })] }));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent(/did not match this company/);
  });

  it('says a 403 plainly and offers to read again after a failure', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rulesFailure: { status: 403, message: 'denied' } }));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('You do not have access to see where designs are used.');
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule()] }));
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Purchase · all types')).toBeInTheDocument();
  });

  it('says a 500 as a failure to read, with the reason', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rulesFailure: { status: 500, message: 'The design service is unavailable.' } }));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('Where this design is used could not be read. The design service is unavailable.');
  });

  it('is not drawn at all without routing read access, and asks nothing', () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    mount({ read: false });
    expect(screen.queryByText('Used for')).toBeNull();
    expect(serviceCall).not.toHaveBeenCalled();
  });

  it('lists without any control for a reader who cannot manage routing', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule()] }));
    mount({ manage: false });
    expect(await screen.findByText('Purchase · all types')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Use for a Purchase type/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Stop using/ })).toBeNull();
  });

  it('offers no Stop on an organisation-wide rule, and says whose it is', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule({ company_id: TENANT_WIDE })] }));
    mount();
    expect(await screen.findByText('Set for your whole organisation')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop using/ })).toBeNull();
  });
});

describe('using it for a Purchase type', () => {
  it('uses it for one active Purchase type, then lists it and tells the print checks', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    const onChanged = mount();
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    const choose = screen.getByRole('combobox', { name: 'Purchase vouchers to use this design for' });
    await waitFor(() => expect(within(choose).getByRole('option', { name: 'Goods bill' })).toBeInTheDocument());
    // A retired type is not offered.
    expect(within(choose).queryByRole('option', { name: 'Old bill' })).toBeNull();
    await user.selectOptions(choose, 'Goods bill');
    await user.click(screen.getByRole('button', { name: 'Use for Purchase · Goods bill' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toMatchObject({
      service: 'design',
      method: 'POST',
      path: `/v1/companies/${COMPANY}/assignments`,
      body: { voucher_kind: 'PURCHASE', template_id: TEMPLATE, priority: 100, voucher_type_id: GOODS },
    });
    expect(await screen.findByText('Now used for Purchase · Goods bill.')).toBeInTheDocument();
    expect(await screen.findByText('Purchase · Goods bill')).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('uses it for all Purchase types with no type on the rule', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount({ types: false });
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    expect(screen.getByText('Choosing one Purchase type needs access to read voucher types.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Use for Purchase · all types' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]!.body).toEqual({ voucher_kind: 'PURCHASE', template_id: TEMPLATE, priority: 100 });
  });

  it('shows the write as pending, and holds the buttons while it is', async () => {
    let finish: (value: unknown) => void = () => undefined;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (request.method === 'POST') return new Promise((resolve) => { finish = resolve; }) as never;
      return responder()(endpoint, request);
    });
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    await user.click(screen.getByRole('button', { name: 'Use for Purchase · all types' }));
    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    finish(rule());
    expect(await screen.findByText('Now used for Purchase · all types.')).toBeInTheDocument();
  });

  it('says a duplicate plainly, with where to stop the other design', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ createFailure: { status: 409, message: 'an active rule already matches exactly these criteria' } }));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    await user.click(screen.getByRole('button', { name: 'Use for Purchase · all types' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Another design is already used for Purchase · all types. Stop using that one first — on Purchase print — then use this design.');
    expect(within(alert).getByRole('link', { name: 'Open Purchase print' })).toHaveAttribute('href', '/documents/vouchers/purchase');
  });

  it.each([
    [403, 'You may not route documents here.'],
    [422, 'voucher_type_id: the voucher type is not a Purchase type'],
    [500, 'The design service is unavailable. Try again.'],
  ])('shows a %s refusal and keeps the choice open', async (status, message) => {
    vi.mocked(serviceCall).mockImplementation(responder({ createFailure: { status, message } }));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    await user.click(screen.getByRole('button', { name: 'Use for Purchase · all types' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(screen.getByRole('combobox', { name: 'Purchase vouchers to use this design for' })).toBeInTheDocument();
  });

  it('can be cancelled without writing anything', async () => {
    vi.mocked(serviceCall).mockImplementation(responder());
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Use for a Purchase type…' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Use for a Purchase type…' })).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });
});

describe('stopping', () => {
  it('asks first, then retires the rule and says so', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule()] }));
    const user = userEvent.setup();
    const onChanged = mount();
    await user.click(await screen.findByRole('button', { name: 'Stop using for Purchase · all types' }));
    const dialog = await screen.findByRole('dialog', { name: 'Stop using this design for Purchase · all types?' });
    await user.click(within(dialog).getByRole('button', { name: 'Stop using' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toMatchObject({ method: 'PATCH', path: `/v1/companies/${COMPANY}/assignments/${RULE}`, body: { is_active: false } });
    expect(await screen.findByText('No longer used for Purchase · all types.')).toBeInTheDocument();
    expect(await screen.findByTestId('usage-empty')).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it('keeps the dialog open with the reason when stopping fails', async () => {
    vi.mocked(serviceCall).mockImplementation(responder({ rules: [rule()], stopFailure: { status: 403, message: 'You may not change routing here.' } }));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Stop using for Purchase · all types' }));
    const dialog = await screen.findByRole('dialog', { name: /Stop using this design/ });
    await user.click(within(dialog).getByRole('button', { name: 'Stop using' }));
    expect(await within(dialog).findByText('You may not change routing here.')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.getByText('Purchase · all types')).toBeInTheDocument();
  });
});

describe('the words for a rule', () => {
  it('says every condition a rule pins', () => {
    const name = (id: string) => (id === GOODS ? 'Goods bill' : undefined);
    expect(usageLabel(rule() as never, name)).toBe('Purchase · all types');
    expect(usageLabel(rule({ voucher_type_id: GOODS, branch_id: OTHER, customer_tax_category: 'B2B', specific_version_id: OTHER }) as never, name))
      .toBe('Purchase · Goods bill · one branch · tax category B2B · pinned to one version');
    expect(usageLabel(rule({ voucher_type_id: SERVICES }) as never, name)).toBe('Purchase · one voucher type');
  });
});

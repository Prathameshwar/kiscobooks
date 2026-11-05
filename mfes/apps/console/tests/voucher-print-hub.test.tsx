/**
 * Voucher print — a card for every kind of voucher.
 *
 * Nothing on this page needs setting up: every voucher prints on the standard layout. What is
 * worth testing is not that cards render but the ways a card can mislead:
 *
 *  - **A missing card.** The page is the only way in to "give a receipt a layout of my own", so a
 *    kind without a card cannot be customized at all. Every kind of the vocabulary has one, once.
 *  - **A false "Custom layout".** The chip claims the voucher prints on something other than the
 *    standard layout. A retired rule routes nothing, and a rule on a template with no published
 *    version is skipped when a document resolves — so neither may earn the chip. And a chip read off
 *    a list that has a second page is a claim nobody can stand behind, so it is withheld.
 *  - **A gate that is not one.** The chip needs routing read access; the cards do not. A reader
 *    without it gets every card and no chip, never a blank page and never a guess.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionProvider } from '@janso/ui';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { VoucherPrintHub } from '../app/components/VoucherPrintHub';
import { VOUCHER_KINDS, VOUCHER_KIND_GROUPS, kindSlug } from '../app/lib/voucher-kinds';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const ONE = '01990000-0000-7000-8000-000000000001';
const TWO = '01990000-0000-7000-8000-000000000002';
const DRAFT = '01990000-0000-7000-8000-000000000003';
const GONE = '01990000-0000-7000-8000-000000000004';
const FIRST_PAGE = { limit: 200, has_more: false, next_cursor: null };
const MORE = { limit: 200, has_more: true, next_cursor: 'next' };

function rule(kind: string, template: string, overrides: Record<string, unknown> = {}) {
  return {
    id: crypto.randomUUID(),
    company_id: COMPANY,
    voucher_kind: kind,
    template_id: template,
    priority: 100,
    is_active: true,
    created_at: '2026-10-27T00:00:00Z',
    ...overrides,
  };
}

function template(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    company_id: COMPANY,
    code: `code-${id.slice(-1)}`,
    name: `Template ${id.slice(-1)}`,
    status: 'PUBLISHED',
    current_version_id: '01990000-0000-7000-8000-00000000000a',
    ...overrides,
  };
}

/** Two published templates, a draft, and nothing else — unless a test says so. */
const TEMPLATES = [template(ONE), template(TWO), template(DRAFT, { status: 'DRAFT', current_version_id: null })];

type Answers = { rules?: unknown[]; templates?: unknown[]; rulesPage?: unknown; templatesPage?: unknown };

function answer({ rules = [], templates = TEMPLATES, rulesPage = FIRST_PAGE, templatesPage = FIRST_PAGE }: Answers = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    return (path.endsWith('/assignments') ? { items: rules, page: rulesPage } : { items: templates, page: templatesPage }) as never;
  };
}

function mount({ canManage = true, canReadRouting = true } = {}) {
  return render(
    <PermissionProvider permissions={['design.template.read']}>
      <VoucherPrintHub company={COMPANY} canManage={canManage} canReadRouting={canReadRouting} />
    </PermissionProvider>,
  );
}

const card = (title: string) => screen.getByRole('link', { name: title });
/** Lets a settled request's state updates land, for asserting something did *not* appear. */
const settled = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
const requests = () => vi.mocked(serviceCall).mock.calls.map(([, request]) => request.path);

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
});

describe('the cards', () => {
  it('gives every kind of voucher a card, once, under its own family', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findAllByText('Standard layout');

    expect(document.querySelectorAll('a.janso-action-card')).toHaveLength(VOUCHER_KINDS.length);
    for (const group of VOUCHER_KIND_GROUPS) {
      const region = screen.getByRole('region', { name: group.title });
      expect(within(region).getAllByRole('link')).toHaveLength(group.kinds.length);
    }
  });

  it('sends each card to its own kind', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findAllByText('Standard layout');

    expect(card('Sales')).toHaveAttribute('href', '/documents/vouchers/sales');
    expect(card('Credit note')).toHaveAttribute('href', '/documents/vouchers/credit-note');
    expect(card('Job-work order in')).toHaveAttribute('href', '/documents/vouchers/job-work-in-order');
    for (const { value } of VOUCHER_KINDS) {
      expect(document.querySelector(`a[href="/documents/vouchers/${kindSlug(value)}"]`), value).not.toBeNull();
    }
  });

  it('says what each voucher is, as a sentence', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();

    expect(await screen.findByText('Invoice, cash or credit sale.')).toBeInTheDocument();
    expect(screen.getByText('Time-bounded what-if adjustment.')).toBeInTheDocument();
  });

  it('puts the page in its place, says nothing needs setting up, and offers the voucher types', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findAllByText('Standard layout');

    expect(screen.getByRole('heading', { level: 1, name: 'Voucher print' })).toBeInTheDocument();
    expect(screen.getByText('Vouchers print on the standard layout until a layout is set for them. Choose one to give it a layout of your own.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Manage voucher types' })).toHaveAttribute('href', '/masters/voucher-types');
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(within(crumbs).getByRole('link', { name: 'Print templates' })).toHaveAttribute('href', '/invoice-designer');
  });

  it('does not put routing, which nobody needs to print, in the header', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findAllByText('Standard layout');

    expect(screen.queryByRole('link', { name: /routing/i })).not.toBeInTheDocument();
  });

  it('changes only the verb for a reader who may not design', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount({ canManage: false });
    await screen.findAllByText('Standard layout');

    expect(within(card('Sales')).getByText('View print')).toBeInTheDocument();
    expect(screen.queryByText('Design print')).not.toBeInTheDocument();
    // …and the card still opens: reading a layout is what the page is gated on.
    expect(card('Sales')).toHaveAttribute('href', '/documents/vouchers/sales');
  });
});

describe('which vouchers have a layout of their own', () => {
  it('says Standard layout for every voucher while nothing is customized — a state, not a gap', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();

    await screen.findAllByText('Standard layout');
    expect(screen.getAllByText('Standard layout')).toHaveLength(VOUCHER_KINDS.length);
    expect(screen.getAllByText('Standard layout')[0]).toHaveAttribute('data-tone', 'neutral');
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it('says Custom layout for a kind routed to a published template, and only that kind', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE), rule('RECEIPT', TWO, { currency_code: 'USD' })] }));
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toHaveAttribute('data-tone', 'success');
    // Receipt has only a rule for USD documents: not a layout for every receipt.
    expect(within(card('Receipt')).getByText('Custom for some documents')).toBeInTheDocument();
    expect(within(card('Journal')).getByText('Standard layout')).toHaveAttribute('data-tone', 'neutral');
    expect(screen.getAllByText('Custom layout')).toHaveLength(1);
  });

  it('says it once, however many rules and templates a kind has', async () => {
    vi.mocked(serviceCall).mockImplementation(
      answer({ rules: [rule('SALES', ONE), rule('SALES', ONE, { currency_code: 'USD' }), rule('SALES', TWO)] }),
    );
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
    expect(screen.getAllByText('Custom layout')).toHaveLength(1);
  });

  it('does not say it for a retired rule — it routes nothing', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE, { is_active: false })] }));
    mount();

    expect(await within(card('Sales')).findByText('Standard layout')).toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it('does not say it for a template still being designed — a draft is skipped when a document resolves', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', DRAFT)] }));
    mount();

    expect(await within(card('Sales')).findByText('Standard layout')).toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it('does not say it for a template that cannot be found', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', GONE)] }));
    mount();

    expect(await within(card('Sales')).findByText('Standard layout')).toBeInTheDocument();
  });

  it('says it for a rule that outlives a draft once the template is published', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', DRAFT)], templates: [template(DRAFT)] }));
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
  });

  it('describes a card by its chip, without renaming the link', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE)] }));
    mount();

    await within(card('Sales')).findByText('Custom layout');
    expect(card('Sales')).toHaveAccessibleDescription('Invoice, cash or credit sale. Custom layout');
  });

  it('withholds the chips, and says so, when the rule list runs past one page', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE)], rulesPage: MORE }));
    mount();

    expect(await screen.findByText(/hidden because this company has more rules or templates than fit on one page/)).toBeInTheDocument();
    // A chip off an incomplete page would be a claim nobody can stand behind.
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();
    expect(card('Sales')).toHaveAttribute('href', '/documents/vouchers/sales');
  });

  it('withholds them when the template list runs past one page, too — a template that fell off would read as a draft', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE)], templatesPage: MORE }));
    mount();

    expect(await screen.findByText(/hidden because this company has more rules or templates/)).toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();
  });

  it('asks for retired rules too, and for the templates, once each', async () => {
    vi.mocked(serviceCall).mockImplementation(answer());
    mount();
    await screen.findAllByText('Standard layout');

    expect(serviceCall).toHaveBeenCalledTimes(2);
    expect(vi.mocked(serviceCall).mock.calls.every(([, request]) => request.service === 'design')).toBe(true);
    expect(requests()).toEqual(
      expect.arrayContaining([
        `/v1/companies/${COMPANY}/assignments?include_inactive=true&limit=200`,
        `/v1/companies/${COMPANY}/templates?limit=200`,
      ]),
    );
  });
});

describe('without routing access', () => {
  it('shows every card and never asks for the rules or the templates', async () => {
    mount({ canReadRouting: false });

    expect(await screen.findByRole('link', { name: 'Sales' })).toBeInTheDocument();
    expect(serviceCall).not.toHaveBeenCalled();
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
    // The voucher types are not a routing matter.
    expect(screen.getByRole('link', { name: 'Manage voucher types' })).toBeInTheDocument();
  });

  it('treats a refusal from the service as no chips, not as a fault', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'forbidden' });
    mount();

    expect(await screen.findByRole('link', { name: 'Sales' })).toBeInTheDocument();
    await settled();
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();
    expect(screen.queryByText(/could not be loaded/)).not.toBeInTheDocument();
    expect(screen.queryByText(/hidden because/)).not.toBeInTheDocument();
  });
});

describe('when the chips fail', () => {
  it('keeps every card, says why the chips are missing, and offers a retry for both lists', async () => {
    vi.mocked(serviceCall).mockRejectedValueOnce({ status: 500, message: 'boom' });
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE)] }));
    const user = userEvent.setup();
    mount();

    expect(await screen.findByText(/Which vouchers have a custom layout could not be loaded/)).toBeInTheDocument();
    expect(card('Sales')).toHaveAttribute('href', '/documents/vouchers/sales');
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
    expect(screen.queryByText(/could not be loaded/)).not.toBeInTheDocument();
  });

  it('does the same when it is the template list that fails', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (request.path.split('?')[0]!.endsWith('/templates')) throw { status: 500, message: 'boom' };
      return (await answer()(endpoint, request)) as never;
    });
    mount();

    expect(await screen.findByText(/Which vouchers have a custom layout could not be loaded/)).toBeInTheDocument();
    expect(screen.queryByText('Standard layout')).not.toBeInTheDocument();
    expect(card('Sales')).toHaveAttribute('href', '/documents/vouchers/sales');
  });
});

describe('agreeing with the voucher’s own page', () => {
  const ORG = '00000000-0000-0000-0000-000000000000';

  it('says Custom for some documents when only rules for particular cases are in force — not Custom layout for everything', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('RECEIPT', ONE, { currency_code: 'USD' })] }));
    mount();

    expect(await within(card('Receipt')).findByText('Custom for some documents')).toHaveAttribute('data-tone', 'info');
    expect(screen.queryByText('Custom layout')).not.toBeInTheDocument();
  });

  it('says Custom layout, not the lesser, when a default and a case-specific rule are both in force', async () => {
    vi.mocked(serviceCall).mockImplementation(answer({ rules: [rule('SALES', ONE), rule('SALES', TWO, { currency_code: 'USD' })] }));
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
    expect(within(card('Sales')).queryByText('Custom for some documents')).not.toBeInTheDocument();
  });

  it('says Custom layout for a kind whose default was set for the whole organisation', async () => {
    vi.mocked(serviceCall).mockImplementation(
      answer({ rules: [rule('SALES', ONE, { company_id: ORG })], templates: [template(ONE, { company_id: ORG })] }),
    );
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
  });

  it('does not say it for an organisation default on a template that is only a draft', async () => {
    vi.mocked(serviceCall).mockImplementation(
      answer({
        rules: [rule('SALES', DRAFT, { company_id: ORG })],
        templates: [template(DRAFT, { company_id: ORG, status: 'DRAFT', current_version_id: null })],
      }),
    );
    mount();

    expect(await within(card('Sales')).findByText('Standard layout')).toBeInTheDocument();
  });

  it('does not let a draft hide the published default beneath it', async () => {
    // The company's draft outranks the organisation's published layout, and is skipped when a document resolves.
    vi.mocked(serviceCall).mockImplementation(
      answer({
        rules: [rule('SALES', DRAFT, { priority: 500 }), rule('SALES', ONE, { company_id: ORG })],
        templates: [template(ONE, { company_id: ORG }), template(DRAFT, { status: 'DRAFT', current_version_id: null })],
      }),
    );
    mount();

    expect(await within(card('Sales')).findByText('Custom layout')).toBeInTheDocument();
  });
});

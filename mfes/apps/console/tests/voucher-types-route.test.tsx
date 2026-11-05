/**
 * `/masters/voucher-types/…` as the server resolves it.
 *
 * The pages are tested on their own; what only the route decides is *which* page a URL is, and
 * *whether this person gets it*. A segment that is not a type id is a 404 rather than a request to
 * the service with a stranger's text in its path; reading needs `vouchers.read` for the open
 * company, and every page that writes needs `vouchers.type.manage` as well — held for this company,
 * not merely somewhere.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children, activeHref }: { children: React.ReactNode; activeHref: string }) => <div data-active={activeHref}>{children}</div>,
}));
const show = (name: string) => (props: Record<string, unknown>) => <p>{name} {JSON.stringify(props)}</p>;
vi.mock('../app/components/VoucherTypeDirectory', () => ({ VoucherTypeDirectory: (props: Record<string, unknown>) => show('Directory')(props) }));
vi.mock('../app/components/VoucherTypeEditor', () => ({ VoucherTypeEditor: (props: Record<string, unknown>) => show('Editor')(props) }));
vi.mock('../app/components/VoucherTypeDetail', () => ({ VoucherTypeDetail: (props: Record<string, unknown>) => show('Detail')(props) }));
vi.mock('../app/components/VoucherTypeRulesEditor', () => ({ VoucherTypeRulesEditor: (props: Record<string, unknown>) => show('Rules')(props) }));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('NEXT_NOT_FOUND');
  },
}));

import { VoucherTypesRoute } from '../app/components/VoucherTypesRoute';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const ID = '01990000-0000-7000-8000-0000000000a1';
const READ = 'vouchers.read';
const MANAGE = 'vouchers.type.manage';

async function open(permissions: string[], { scope = COMPANY, company = COMPANY as string | null } = {}) {
  const session = await sessionFor();
  session.company = company ? { id: company, name: 'Current company' } : { id: undefined, name: '' };
  session.grants = [{ scope_type: 'company', scope_id: scope, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}
const props = (prefix: string) => JSON.parse(screen.getByText(new RegExp('^' + prefix + ' ')).textContent!.slice(prefix.length + 1));
const go = async (record: string[], query: Record<string, string | string[] | undefined> = {}) => render(await VoucherTypesRoute({ record, query }));

beforeEach(() => {
  vi.mocked(pageContext).mockReset();
});

describe('which page a URL is', () => {
  it('is the list at the root, inside the shell, with manage as a flag', async () => {
    await open([READ]);
    await go([]);

    expect(props('Directory')).toEqual({ company: COMPANY, canManage: false });
    expect(document.querySelector('[data-active]')).toHaveAttribute('data-active', '/masters/voucher-types');
  });

  it('is the create form at /new, and a copy form when it names a source', async () => {
    await open([READ, MANAGE]);
    await go(['new']);
    expect(props('Editor')).toEqual({ company: COMPANY });
    document.body.innerHTML = '';
    await go(['new'], { from: ID });
    expect(props('Editor')).toEqual({ company: COMPANY, from: ID });
  });

  it('is one type at /<id>, carrying what it was just told', async () => {
    await open([READ, MANAGE]);
    await go([ID], { saved: 'created' });

    expect(props('Detail')).toEqual({ company: COMPANY, id: ID, canManage: true, saved: 'created' });
  });

  it('is the rules form at /<id>/edit', async () => {
    await open([READ, MANAGE]);
    await go([ID, 'edit']);

    expect(props('Rules')).toEqual({ company: COMPANY, id: ID });
  });

  it('lowers an upper-case id, since ids are lower case on the wire and a response is compared with the id asked for', async () => {
    await open([READ, MANAGE]);
    await go([ID.toUpperCase()]);
    expect(props('Detail').id).toBe(ID);
    document.body.innerHTML = '';
    await go([ID.toUpperCase(), 'edit']);
    expect(props('Rules').id).toBe(ID);
    document.body.innerHTML = '';
    await go(['new'], { from: ID.toUpperCase() });
    expect(props('Editor').from).toBe(ID);
  });

  it('ignores a repeated ?saved=, rather than passing an array on', async () => {
    await open([READ]);
    await go([ID], { saved: ['created', 'retired'] });

    expect(props('Detail').saved).toBeUndefined();
  });
});

describe('what is not a page', () => {
  it.each([
    [['nope']],
    [['edit']],
    [[ID, 'nope']],
    [[ID, 'edit', 'more']],
    [['new', 'edit']],
    [['new', ID]],
    [[ID.toUpperCase().slice(0, 30)]],
    [['..']],
  ])('is a 404 for %j, before the session is even looked at', async (record) => {
    await open([READ, MANAGE]);

    await expect(VoucherTypesRoute({ record, query: {} })).rejects.toThrow('NEXT_NOT_FOUND');
    expect(pageContext).not.toHaveBeenCalled();
  });

  it.each(['nope', ID + 'x', '../' + ID, ''])('is a 404 for a copy of %j — not a source', async (from) => {
    await open([READ, MANAGE]);

    await expect(VoucherTypesRoute({ record: ['new'], query: { from } })).rejects.toThrow('NEXT_NOT_FOUND');
  });

  it('is a 404 for two sources, rather than a blank form that ignores them', async () => {
    await open([READ, MANAGE]);

    await expect(VoucherTypesRoute({ record: ['new'], query: { from: [ID, ID] } })).rejects.toThrow('NEXT_NOT_FOUND');
  });
});

describe('who gets a page', () => {
  it('needs voucher read access for the list, a type, and the forms alike', async () => {
    await open([MANAGE]);
    for (const [record, query] of [[[], {}], [[ID], {}], [['new'], {}], [[ID, 'edit'], {}]] as const) {
      document.body.innerHTML = '';
      await go([...record], query);
      expect(screen.getByText(/Voucher read access is required for this company/), record.join('/')).toBeInTheDocument();
      expect(screen.queryByText(/^(Directory|Detail|Editor|Rules) /)).not.toBeInTheDocument();
    }
  });

  it('needs the manage permission as well to start, copy or change a type', async () => {
    await open([READ]);
    for (const [record, query] of [[['new'], {}], [['new'], { from: ID }], [[ID, 'edit'], {}]] as const) {
      document.body.innerHTML = '';
      await go([...record], query);
      expect(screen.getByText(/voucher type manage permission is required/), record.join('/')).toBeInTheDocument();
    }
  });

  it('lets a reader see the list and a type, without the manage flag', async () => {
    await open([READ]);
    await go([ID]);
    expect(props('Detail').canManage).toBe(false);
  });

  it('is refused when the grant is for another company', async () => {
    await open([READ, MANAGE], { scope: OTHER });
    await go([]);

    expect(screen.getByText(/Voucher read access is required for this company/)).toBeInTheDocument();
  });

  it('says there is nothing to manage when no company is open', async () => {
    await open([READ, MANAGE], { company: null });
    await go([]);

    expect(screen.getByText(/No company is open, so there is nothing to manage voucher types for yet/)).toBeInTheDocument();
  });
});

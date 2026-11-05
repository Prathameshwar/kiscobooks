/**
 * The two Voucher print routes, as the server renders them.
 *
 * The components are tested on their own; what only these files decide is *whether a person gets
 * one at all* — an unknown voucher segment is a 404 rather than a guess at the nearest kind, the
 * page needs company-scoped `design.template.read` (a grant held for another company does not
 * open this one), and each permission reaches the component as exactly the flag it names.
 */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children, activeHref }: { children: React.ReactNode; activeHref: string }) => (
    <div data-active={activeHref}>{children}</div>
  ),
}));
vi.mock('../app/components/VoucherPrintHub', () => ({
  VoucherPrintHub: (props: Record<string, unknown>) => <p>Hub {JSON.stringify(props)}</p>,
}));
vi.mock('../app/components/VoucherPrintKind', () => ({
  VoucherPrintKind: (props: Record<string, unknown>) => <p>Kind {JSON.stringify(props)}</p>,
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('NEXT_NOT_FOUND');
  },
}));

import HubPage, { metadata } from '../app/documents/vouchers/page';
import KindPage, { generateMetadata } from '../app/documents/vouchers/[kind]/page';

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const READ = 'design.template.read';
const ALL = [READ, 'design.template.manage', 'design.assignment.read', 'design.assignment.manage'];

async function open(permissions: string[], { scope = COMPANY, company = COMPANY as string | null } = {}) {
  const session = await sessionFor();
  session.company = company ? { id: company, name: 'Current company' } : { id: undefined, name: '' };
  session.grants = [{ scope_type: 'company', scope_id: scope, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
}

const params = (kind: string) => ({ params: Promise.resolve({ kind }) });
const props = (text: string) => JSON.parse(text.slice(text.indexOf('{')));

beforeEach(() => vi.mocked(pageContext).mockReset());

describe('the card page', () => {
  it('opens for company-scoped template read access, inside the shell, with each flag as its permission', async () => {
    await open([READ, 'design.assignment.read']);
    render(await HubPage());

    expect(props(screen.getByText(/^Hub /).textContent!)).toEqual({
      company: COMPANY,
      canManage: false,
      canReadRouting: true,
    });
    expect(document.querySelector('[data-active]')).toHaveAttribute('data-active', '/documents/vouchers');
  });

  it('passes template manage on as canManage, and nothing more', async () => {
    await open(ALL);
    render(await HubPage());

    expect(props(screen.getByText(/^Hub /).textContent!)).toMatchObject({ canManage: true, canReadRouting: true });
  });

  it('is refused without template read, even to someone who may route', async () => {
    await open(['design.assignment.read', 'design.assignment.manage']);
    render(await HubPage());

    expect(screen.queryByText(/^Hub /)).not.toBeInTheDocument();
    expect(screen.getByText(/Template read access is required for this company/)).toBeInTheDocument();
  });

  it('is refused when the grant is for another company', async () => {
    await open(ALL, { scope: OTHER });
    render(await HubPage());

    expect(screen.queryByText(/^Hub /)).not.toBeInTheDocument();
    expect(screen.getByText(/Template read access is required for this company/)).toBeInTheDocument();
  });

  it('says there is nothing to design for when no company is open', async () => {
    await open(ALL, { company: null });
    render(await HubPage());

    expect(screen.queryByText(/^Hub /)).not.toBeInTheDocument();
    expect(screen.getByText(/No company is open, so there is nothing to design voucher prints for yet/)).toBeInTheDocument();
  });

  it('carries its own title', () => {
    expect(metadata.title).toBe('Voucher print · KiscoBooks');
  });
});

describe('a voucher kind’s page', () => {
  it('opens the kind its segment names, with one flag per permission', async () => {
    await open(ALL);
    render(await KindPage(params('credit-note')));

    expect(props(screen.getByText(/^Kind /).textContent!)).toEqual({
      company: COMPANY,
      kind: 'CREDIT_NOTE',
      canManageTemplates: true,
      canReadRouting: true,
      canManageRouting: true,
    });
    expect(document.querySelector('[data-active]')).toHaveAttribute('data-active', '/documents/vouchers');
  });

  it('keeps template authoring and routing apart', async () => {
    await open([READ, 'design.template.manage', 'design.assignment.read']);
    render(await KindPage(params('sales')));

    expect(props(screen.getByText(/^Kind /).textContent!)).toMatchObject({
      canManageTemplates: true,
      canReadRouting: true,
      canManageRouting: false,
    });
  });

  it.each(['nonsense', 'SALES', 'credit_note', '', 'sales%2F..%2Frouting'])('is a 404 for the segment %j', async (segment) => {
    await open(ALL);

    await expect(KindPage(params(segment))).rejects.toThrow('NEXT_NOT_FOUND');
    await expect(generateMetadata(params(segment))).rejects.toThrow('NEXT_NOT_FOUND');
  });

  it('does not look at the session for a segment that names no kind', async () => {
    await open(ALL);

    await expect(KindPage(params('nonsense'))).rejects.toThrow();
    expect(pageContext).not.toHaveBeenCalled();
  });

  it('is refused without template read', async () => {
    await open(['design.assignment.read']);
    render(await KindPage(params('sales')));

    expect(screen.queryByText(/^Kind /)).not.toBeInTheDocument();
    expect(screen.getByText(/Template read access is required for this company/)).toBeInTheDocument();
  });

  it('says there is nothing to design for when no company is open', async () => {
    await open(ALL, { company: null });
    render(await KindPage(params('sales')));

    expect(screen.queryByText(/^Kind /)).not.toBeInTheDocument();
    expect(screen.getByText(/No company is open/)).toBeInTheDocument();
  });

  it('titles the page for the voucher', async () => {
    await expect(generateMetadata(params('stock-journal'))).resolves.toMatchObject({
      title: 'Stock journal print · KiscoBooks',
    });
  });
});
